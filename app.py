from flask import Flask, request, jsonify, abort
import os
import tempfile
import requests
from pdf2image import convert_from_path
import pytesseract
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import cv2
import numpy as np
import pdfplumber

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Retrieve environment variables
ENABLE_KEY = os.getenv('ENABLE_KEY', 'False').lower() in ('true', '1', 't')
SECRET_KEY = os.getenv('KEY')
MAX_TIMEOUT = int(os.getenv('MAX_TIMEOUT', 300))  # Default timeout to 300 seconds


# Preprocess image to improve OCR accuracy
def preprocess_image(image):
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


# Function to perform OCR on PDF and return text
def ocr_pdf(pdf_path):
    ocr_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            elements = []

            # Step 1: Extract text elements
            page_text = page.extract_text()
            if page_text:
                elements.append({
                    'type': 'text',
                    'y0': 0.0,  # Text spans the whole page, so we start at y0 = 0.0
                    'content': page_text
                })

            # Step 2: Extract tables as elements
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    table_text = '\n'.join(['\t'.join([str(cell) if cell is not None else '' for cell in row]) for row in table])
                    try:
                        y0_value = float(table[0][0][1])
                    except (ValueError, TypeError):
                        y0_value = 0.0  # Default to 0.0 if conversion fails
                    elements.append({
                        'type': 'table',
                        'y0': y0_value,  # Use validated y0
                        'content': table_text
                    })

            # Step 3: Extract images and run OCR
            for img in page.images:
                page_image = page.to_image()
                try:
                    cropped_image = page_image.original.crop((img['x0'], img['y0'], img['x1'], img['y1']))
                    processed_image = preprocess_image(cropped_image)
                    img_text = pytesseract.image_to_string(processed_image)
                    elements.append({
                        'type': 'image',
                        'y0': float(img['y0']),  # Ensure y0 is a float
                        'content': img_text
                    })
                except (KeyError, ValueError, TypeError):
                    continue  # Skip this image if any errors occur

            # Step 4: Sort all elements by their vertical position
            elements.sort(key=lambda x: x['y0'])

            # Step 5: Combine all elements in the correct order
            for element in elements:
                ocr_text += "\n\n" + element['content'] + "\n\n"

            # Step 6: If no text, tables, or images were found, run OCR on the entire page
            if not elements:
                page_image = page.to_image()
                processed_image = preprocess_image(page_image.original)
                page_ocr_text = pytesseract.image_to_string(processed_image)
                ocr_text += page_ocr_text + "\n\n"

    return ocr_text


# Middleware to check for valid key
def check_key():
    if ENABLE_KEY:
        key = request.args.get('key') if request.method == 'GET' else request.form.get('key')
        if not key or key != SECRET_KEY:
            abort(403, description="Invalid or missing API key")


# Endpoint to handle both POST and GET requests
@app.route('/recognize', methods=['POST', 'GET'])
def recognize():
    check_key()

    try:
        if request.method == 'POST':
            if 'file' not in request.files:
                return jsonify({"error": "No file part"}), 400
            file = request.files['file']
            if file.filename == '':
                return jsonify({"error": "No selected file"}), 400
            if file:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                    file.save(temp_pdf.name)
                    ocr_text = ocr_pdf(temp_pdf.name)
                os.remove(temp_pdf.name)  # Ensure the temporary file is deleted
                return jsonify({"ocr_text": ocr_text}), 200

        elif request.method == 'GET':
            file_url = request.args.get('file')
            if not file_url:
                return jsonify({"error": "No URL provided"}), 400
            else:
                response = requests.get(file_url, timeout=MAX_TIMEOUT)
                if response.status_code == 200:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                        temp_pdf.write(response.content)
                        ocr_text = ocr_pdf(temp_pdf.name)
                    os.remove(temp_pdf.name)  # Ensure the temporary file is deleted
                    return jsonify({"ocr_text": ocr_text}), 200
                else:
                    return jsonify({
                        "error": "Unable to download the file",
                        "status_code": response.status_code,
                        "reason": response.reason,
                        "url": file_url
                    }), 400

    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "An error occurred while downloading the file",
            "details": str(e)
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)