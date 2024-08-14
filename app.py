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
            # Extract text
            page_text = page.extract_text()
            if page_text:
                ocr_text += page_text

            # Extract tables (if any)
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    table_text = '\n'.join(['\t'.join(row) for row in table])
                    ocr_text += "\n\n" + table_text + "\n\n"

            # Perform OCR on images in the PDF
            for img in page.images:
                page_image = page.to_image().crop(img['bbox'])
                processed_image = preprocess_image(page_image.original)
                ocr_text += pytesseract.image_to_string(processed_image)
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