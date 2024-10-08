# Use Ubuntu 22.04 as the base image
FROM ubuntu:22.04

# Update the package list and install necessary packages
RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository universe && \
    apt-get update && \
    apt-get install -y \
        tesseract-ocr \
        python3-pip \
        poppler-utils \
        wget \
        git \
        libxml2-dev \
        libxslt1-dev \
        libz-dev \
        libjpeg-dev \
        zlib1g-dev \
        libgl1-mesa-glx \
        imagemagick \
        libmagickwand-dev && \
    apt-get clean

# Allow PDF processing by modifying the ImageMagick policy.xml
RUN sed -i 's/rights="none"/rights="read|write"/g' /etc/ImageMagick-6/policy.xml && \
    sed -i 's/<policy domain="coder" rights="none" pattern="PDF"/<policy domain="coder" rights="read|write" pattern="PDF"/g' /etc/ImageMagick-6/policy.xml

# Set the working directory
WORKDIR /app

# Copy the requirements.txt file
COPY requirements.txt /app/

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the app's code into the container
COPY . /app/

# Copy .env file to the container
COPY .env /app/

# Expose the port
EXPOSE 8080

# Run the application
CMD ["python3", "app.py"]