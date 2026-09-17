# Base image: lightweight Python runtime for the flaky app.
FROM python:3.12-slim

# Set the working directory inside the container.
WORKDIR /app

# Install app dependencies before copying the source code.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the image.
COPY main.py .

# Expose the port used by the FastAPI app.
EXPOSE 8000

# Start the API server when the container runs.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]