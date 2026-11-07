FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends antiword catdoc poppler-utils tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements-tested.txt ./
COPY app app
COPY alembic.ini .
COPY migrations migrations
RUN pip install --no-cache-dir -c requirements-tested.txt .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
