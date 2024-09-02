import os
import tempfile
import requests
from flask import Flask, request, jsonify, abort, render_template_string
from dotenv import load_dotenv
import fitz
import pymupdf4llm

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Retrieve environment variables
ENABLE_KEY = os.getenv('ENABLE_KEY', 'False').lower() in ('true', '1', 't')
SECRET_KEY = os.getenv('KEY')
MAX_TIMEOUT = int(os.getenv('MAX_TIMEOUT', 300))
DPI = int(os.getenv('DPI', 800))
PAGE_WIDTH = int(os.getenv('PAGE_WIDTH', 1224))

def ocr_pdf(pdf_path):
    # Use pymupdf4llm to convert PDF to markdown
    md_text = pymupdf4llm.to_markdown(pdf_path, dpi=DPI, page_width=PAGE_WIDTH)
    return md_text

# Middleware to check for valid key
def check_key():
    if ENABLE_KEY:
        key = request.args.get('key') if request.method == 'GET' else request.form.get('key')
        if not key or key != SECRET_KEY:
            abort(403, description="Invalid or missing API key")

def handle_response(content, status_code):
    output_format = request.args.get('output', 'json').lower()

    if output_format == 'html':
        if isinstance(content, dict) and 'error' in content:
            html_content = f"<h1>Error</h1><p>{content['error']}</p>"
            if 'details' in content:
                html_content += f"<p>Details: {content['details']}</p>"
        else:
            html_content = f"<pre>{content}</pre>"

        return render_template_string(html_content), status_code
    else:
        if isinstance(content, str):
            return jsonify({"ocr_text": content}), status_code
        else:
            return jsonify(content), status_code

# Endpoint to handle both POST and GET requests
@app.route('/recognize', methods=['POST', 'GET'])
def recognize():
    check_key()

    try:
        if request.method == 'POST':
            if 'file' not in request.files:
                return handle_response("No file part", 400)
            file = request.files['file']
            if file.filename == '':
                return handle_response("No selected file", 400)
            if file:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                    file.save(temp_pdf.name)
                    ocr_text = ocr_pdf(temp_pdf.name)
                os.remove(temp_pdf.name)
                return handle_response(ocr_text, 200)

        elif request.method == 'GET':
            file_url = request.args.get('file')
            if not file_url:
                return handle_response("No URL provided", 400)
            else:
                response = requests.get(file_url, timeout=MAX_TIMEOUT)
                if response.status_code == 200:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                        temp_pdf.write(response.content)
                        ocr_text = ocr_pdf(temp_pdf.name)
                    os.remove(temp_pdf.name)
                    return handle_response(ocr_text, 200)
                else:
                    error_message = {
                        "error": "Unable to download the file",
                        "status_code": response.status_code,
                        "reason": response.reason,
                        "url": file_url
                    }
                    return handle_response(error_message, 400)

    except requests.exceptions.RequestException as e:
        error_message = {
            "error": "An error occurred while downloading the file",
            "details": str(e)
        }
        return handle_response(error_message, 500)

# Catch-all route for undefined endpoints
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)