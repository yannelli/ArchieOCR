from flask import Flask, request, jsonify, abort
import os
import tempfile
import requests
from pdf2image import convert_from_path
import pytesseract
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Retrieve environment variables
ENABLE_KEY = os.getenv('ENABLE_KEY', 'False').lower() in ('true', '1', 't')
SECRET_KEY = os.getenv('KEY')
MAX_TIMEOUT = int(os.getenv('MAX_TIMEOUT', 300))  # Default timeout to 300 seconds


# Function to perform OCR on PDF and return text
def ocr_pdf(pdf_path):
    images = convert_from_path(pdf_path)
    ocr_text = ""
    for image in images:
        text = pytesseract.image_to_string(image)
        ocr_text += text
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
            if file and file.filename.endswith('.pdf'):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                    file.save(temp_pdf.name)
                    ocr_text = ocr_pdf(temp_pdf.name)
                os.remove(temp_pdf.name)  # Ensure the temporary file is deleted
                return jsonify({"ocr_text": ocr_text}), 200
            else:
                return jsonify({"error": "File must be a PDF"}), 400

        elif request.method == 'GET':
            file_url = request.args.get('file')
            if not file_url:
                return jsonify({"error": "No URL provided"}), 400
            if file_url.endswith('.pdf'):
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
            else:
                return jsonify({"error": "URL must point to a PDF file"}), 400

    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "An error occurred while downloading the file",
            "details": str(e)
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
