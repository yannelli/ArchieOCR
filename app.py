import os
import tempfile
import requests
from flask import Flask, request, jsonify, abort, render_template_string
from dotenv import load_dotenv
import fitz
from pymupdf4llm import IdentifyHeaders, to_markdown
import pytesseract
from PIL import Image
import io
import re
import cv2
import numpy as np

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Retrieve environment variables
ENABLE_KEY = os.getenv('ENABLE_KEY', 'False').lower() in ('true', '1', 't')
SECRET_KEY = os.getenv('KEY')
MAX_TIMEOUT = int(os.getenv('MAX_TIMEOUT', 300))
DPI = int(os.getenv('DPI', 600))
PAGE_WIDTH = int(os.getenv('PAGE_WIDTH', 1224))
MAX_DPI = 600

def estimate_dpi(image):
    # Get image size in pixels
    width_px, height_px = image.size

    # Get physical size in inches (if available)
    try:
        dpi_x, dpi_y = image.info['dpi']
    except KeyError:
        # If DPI info is not available, assume a default (e.g., 72)
        return 72

    # Calculate and return the average DPI
    return int((dpi_x + dpi_y) / 2)


def preprocess_image(image):
    # Convert PIL Image to numpy array
    img_array = np.array(image)

    # Check if the image is already grayscale
    if len(img_array.shape) == 2 or (len(img_array.shape) == 3 and img_array.shape[2] == 1):
        gray = img_array
    else:
        # Convert to grayscale
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

    # Apply thresholding
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(thresh)


def ocr_image(image):
    # Estimate the DPI
    estimated_dpi = estimate_dpi(image)

    # Preprocess the image
    preprocessed = preprocess_image(image)

    # Calculate the scaling factor
    scale_factor = max(1, estimated_dpi / 72)  # Ensure we don't scale down

    # Resize the image if necessary
    if scale_factor > 1:
        width, height = preprocessed.size
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)
        preprocessed = preprocessed.resize((new_width, new_height), Image.LANCZOS)

    # Perform OCR
    custom_config = r'--oem 3 --psm 3'
    ocr_text = pytesseract.image_to_string(preprocessed, config=custom_config)

    # Post-process the OCR text
    ocr_text = ocr_text.strip()
    ocr_text = re.sub(r'\n+', '\n', ocr_text)  # Remove multiple newlines
    ocr_text = re.sub(r' +', ' ', ocr_text)  # Remove multiple spaces

    return ocr_text


def process_pdf_with_ocr(file_path):
    doc = fitz.open(file_path)
    hdr_info = IdentifyHeaders(file_path)

    full_text = []
    temp_files = []

    for page_number in range(len(doc)):
        # Get markdown text for the page
        md_text = to_markdown(doc, pages=[page_number], hdr_info=hdr_info, write_images=True)

        # Find all image references in the markdown
        image_pattern = r'!\[.*?\]\((.*?)\)'
        image_matches = re.finditer(image_pattern, md_text)

        # Process each image reference
        for match in image_matches:
            image_path = match.group(1)
            # Extract page number and image number from the filename
            parts = image_path.split('-')
            img_num = int(parts[-1].split('.')[0])

            # Get the image from the PDF
            page = doc[page_number]
            image_list = page.get_images(full=True)
            if img_num < len(image_list):
                img_index = image_list[img_num][0]
                base_image = doc.extract_image(img_index)
                image_bytes = base_image["image"]

                # Perform OCR on the image
                image = Image.open(io.BytesIO(image_bytes))
                ocr_text = ocr_image(image)

                # Replace the image reference with OCR text in the markdown
                md_text = md_text.replace(match.group(0), f"\n\n[OCR Text]:\n\n{ocr_text}\n\n")

        full_text.append(md_text)

    doc.close()

    # Clean up any temporary files that might have been created
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            os.remove(temp_file)

    return "\n\n-----\n\n".join(full_text)


def ocr_pdf(pdf_path):
    return process_pdf_with_ocr(pdf_path)


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