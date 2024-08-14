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
import fitz

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Retrieve environment variables
ENABLE_KEY = os.getenv('ENABLE_KEY', 'False').lower() in ('true', '1', 't')
SECRET_KEY = os.getenv('KEY')
MAX_TIMEOUT = int(os.getenv('MAX_TIMEOUT', 300))  # Default timeout to 300 seconds


# Preprocess image to improve OCR accuracy
def preprocess_image(image):
    # Convert to grayscale
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    # Apply adaptive thresholding
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    # Denoise
    denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)
    return denoised


def extract_text_with_pymupdf(pdf_path):
    doc = fitz.open(pdf_path)
    extracted_text = ""

    for i in range(len(doc)):
        page = doc.load_page(i)
        # Use "blocks" to preserve structure better
        blocks = page.get_text("blocks")

        # Sort blocks by their vertical position to preserve layout
        blocks.sort(key=lambda b: b[1])

        for b in blocks:
            extracted_text += f"{b[4]}\n"

        extracted_text += "\n"

    return extracted_text


def ocr_pdf(pdf_path):
    extracted_text = ""

    # First, try to extract text using PyMuPDF
    doc = fitz.open(pdf_path)
    for i in range(len(doc)):
        page = doc.load_page(i)
        blocks = page.get_text("blocks")

        # Sort blocks by their vertical position to maintain layout order
        blocks.sort(key=lambda b: b[1])

        page_text = ""
        for b in blocks:
            page_text += f"{b[4]}\n"

        # If no text is found, or if the text is very sparse, use Tesseract
        if not page_text.strip():
            # Convert page to an image for Tesseract OCR
            pix = page.get_pixmap()
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            processed_image = preprocess_image(img_array)
            page_text = pytesseract.image_to_string(processed_image, config='--psm 6')

        extracted_text += page_text + "\n\n"

    return extracted_text


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


# Catch-all route for undefined endpoints
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
