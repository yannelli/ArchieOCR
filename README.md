# ArchieOCR

## Purpose

The purpose of this project is to provide a quick and easy way to spin up an HTTP API for Tesseract OCR as a Docker image. This API is designed to handle OCR requests for PDF files, making it simple to extract text from PDFs with minimal setup.

## Important Notice

This project is a basic implementation intended for personal or small-scale use. **There are no security features, rate limiting, or advanced protections** beyond a simple API key that can be set in the `.env` file. **Use at your own risk** if deploying in a production environment.

## Acknowledgments

A big thanks to the [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) project for making high-quality OCR accessible and open-source.

## Requirements

- **Docker**: [Install Docker](https://docs.docker.com/get-docker/)
- **Docker Compose**: [Install Docker Compose](https://docs.docker.com/compose/install/)

Please note that this project has only been tested briefly on Linux. Compatibility with other operating systems has not been extensively verified.

## Features

- **Simple API**: Provides a POST endpoint to upload a PDF file and return the OCR text.
- **GET Request Support**: Allows OCR processing of PDFs from a provided URL.
- **Temporary File Handling**: Files are processed within the container’s temporary directory, minimizing permission issues.
- **API Key Support**: Basic security is implemented using an API key that can be set in the `.env` file.

## Usage

### 1. Clone the Repository

```bash
git clone https://github.com/yannelli/ArchieOCR.git
cd ArchieOCR
```

### 2. Create the `.env` File

Create a `.env` file in the project root with the following content:

```env
ENABLE_KEY=True
KEY=your-secret-key
```

### 3. Build and Run the Docker Container

```bash
docker-compose up --build
```

This will build the Docker image and start the container, exposing the service on port `8080`.

### 4. API Endpoints

- **POST /recognize**

  Upload a PDF file for OCR processing.

  ```bash
  curl -X POST -F key=your-secret-key -F file=@/path/to/your/file.pdf http://localhost:8080/recognize
  ```

- **GET /recognize**

  Provide a URL pointing to a PDF file for OCR processing.

  ```bash
  curl "http://localhost:8080/recognize?file=https://example.com/file.pdf&key=your-secret-key"
  ```

### 5. Stopping the Service

To stop the Docker container:

```bash
docker-compose down
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

## Disclaimer

This is a personal project, and I provide no warranty or guarantees of any kind. Use at your own risk.

## Contributions

Contributions are welcome! Feel free to open an issue or submit a pull request.