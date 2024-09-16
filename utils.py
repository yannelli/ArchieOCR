import app
import requests
import re
import filetype
import io
from PIL import Image

VERSION = '1.0'

# regex for http:// or https://
URL_PATTERN = re.compile(r'https?://[^\s\)\]\}]+')
# regex for http:// or https:// markdown links
MD_URL_PATTERN = re.compile(r'\[.*?\]\((https?://[^\s\)\]]+)\)')

# request vars
USER_AGENT = 'ArchieOCR/' + VERSION + ' (https://github.com/yannelli/ArchieOCR)'
DEFAULT_HEADER = {
        'User-Agent': USER_AGENT,
        'Referer': 'None',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        }
REQ_TIMEOUT_SEC = 5
ALLOW_REDIRECT = True


def process_external_image_links(md_text):
    """Processes external image links and replaces them with the OCR results."""
    lines = md_text.split('\n')
    updated_lines = []

    # process each line individually
    for line in lines:
        # To store the positions of already processed URLs (including the appended OCR text)
        processed_positions = []
        # Tracks how much text length changes after each modification
        cumulative_offset = 0
        # Keep the original line to adjust positions correctly
        original_line = line

        # process md links first as the name can be a link and will interfere with basic url regex
        markdown_matches = list(re.finditer(MD_URL_PATTERN, line))
        for match in markdown_matches:
            full_match = match.group(0)
            url = match.group(1)

            if is_image_url(url):
                ocr_text = f"{app.ocr_image(pull_image(url))}"
                # Append the OCR result to the markdown link
                markdown_with_ocr = f"{full_match}: {{{ocr_text}}}"
                # Calculate the shift in position after replacing this markdown link
                shift = len(markdown_with_ocr) - len(full_match)
                # Replace the markdown link in the line
                line = line.replace(full_match, markdown_with_ocr, 1)
                # Track the positions of the entire modified markdown URL (including OCR result)
                start = match.start() + cumulative_offset
                end = start + len(markdown_with_ocr)
                print(f"Markdown start: {start}, end: {end}")
                processed_positions.append((start, end))
                # Update the cumulative offset
                cumulative_offset += shift
            else: # either way position needs to be saved
                processed_positions.append((match.start(), match.end()))

        link_matches = list(re.finditer(URL_PATTERN, original_line))
        for link_match in link_matches:
            url = link_match.group(0)
            start_pos = link_match.start() + cumulative_offset
            end_pos = link_match.end() + cumulative_offset

            is_md_url_overlap = any(start <= start_pos <= end or start <= end_pos <= end for start, end in processed_positions)
            if processed_positions and is_md_url_overlap:
                continue

            if is_image_url(url):
                ocr_text = f"{app.ocr_image(pull_image(url))}"
                shift = len(f"{url}: {{{ocr_text}}}") - len(url)
                line = line.replace(url, f"{url}: {{{ocr_text}}}", 1)

        updated_lines.append(line)

    return '\n'.join(updated_lines)


def pull_image(link: str):
    """Downloads the image and returns a PIL image object."""
    # Download the image and pass to OCR
    try:
        response = requests.get(link, timeout=REQ_TIMEOUT_SEC, headers=DEFAULT_HEADER)
        response.raise_for_status()  # Check for HTTP errors
        return Image.open(io.BytesIO(response.content))  # Load image from URL
    except requests.RequestException as e:
        print(e)
        return None


def get_image_links(txt_array: list[str]) -> list[str]:
    """Extracts and returns all URLs from a list of text lines that point to images."""
    urls = find_links(txt_array)
    image_urls = [url for url in urls if is_image_url(url)]
    return image_urls


def find_links(txt_array: list[str]) -> list[str]:
    """Extracts and returns all URLs from a list of text."""
    all_urls = []
    for txt in txt_array:
        all_urls.extend(re.findall(URL_PATTERN, txt))

    return all_urls


def is_image_url(url: str) -> bool:
    """Checks if a URL points to an image, based on file extension or headers."""
    # try file extension
    if is_image_extension(url):
        return True

    # check header
    try:
        response = requests.head(url, allow_redirects=ALLOW_REDIRECT, timeout=REQ_TIMEOUT_SEC, headers=DEFAULT_HEADER)
        content_type = response.headers.get('Content-Type', '').lower()
        if content_type.startswith('image/'):
            return True
    except requests.RequestException as e:
        print(e)
        pass

    # manually determine filetype
    return is_image_content(url)


def is_image_extension(url: str) -> bool:
    """Checks if a URL has an image file extension."""
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')
    return url.lower().endswith(image_extensions)


def is_image_content(url: str) -> bool:
    """Tries to download a file and check if it is an image based on its content."""
    try:
        response = requests.get(url, stream=True, timeout=5)
        response.raise_for_status()
        header = response.content[:261]
        kind = filetype.guess(header)
        if kind and kind.mime.startswith('image/'):
            return True
    except requests.RequestException as e:
        print(e)
        return False
    return False
