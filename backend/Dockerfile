# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Expose default port (most platforms will override with $PORT)
EXPOSE 5000

# Run Gunicorn using shell form to allow $PORT evaluation
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 3 --access-logfile - --error-logfile - "app:create_app()"
