import shutil
import subprocess
from PIL import Image
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
BINARY_THRESHOLD = 180


def image_smoothening(img):
    ret1, th1 = cv2.threshold(img, BINARY_THRESHOLD, 255, cv2.THRESH_BINARY)
    ret2, th2 = cv2.threshold(th1, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    blur = cv2.GaussianBlur(th2, (1, 1), 0)
    ret3, th3 = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return th3


def remove_noise_and_smooth(img):
    filtered = cv2.adaptiveThreshold(img.astype(np.uint8), 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 41,
                                     3)
    kernel = np.ones((1, 1), np.uint8)
    opening = cv2.morphologyEx(filtered, cv2.MORPH_OPEN, kernel)
    closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, kernel)
    img = image_smoothening(img)
    or_image = cv2.bitwise_or(img, closing)
    return or_image


# Preprocess image to improve OCR accuracy
def preprocess_image(image):
    # Convert to grayscale
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    denoised = remove_noise_and_smooth(gray)
    return denoised


def extract_text_with_pymupdf(pdf_path):
    doc = fitz.open(pdf_path)
    extracted_text = ""

    pytesseract.get_tesseract_version()

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text()
        extracted_text += text

    return extracted_text


def ocr_pdf(pdf_path):
    extracted_text = ""

    page_text = extract_text_with_pymupdf(pdf_path)

    if not page_text.strip():
        images = convert_from_path(pdf_path)

        for i, image in enumerate(images):
            # Preprocess the image
            processed_image = preprocess_image(image)
            processed_text = pytesseract.image_to_string(processed_image, config='--psm 12 --oem 1 --dpi 1200')
            page_text += f"{processed_text}\n\n"

    extracted_text += page_text

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
