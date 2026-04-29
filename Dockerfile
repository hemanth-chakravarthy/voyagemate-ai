# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=7860

# Expose the port Streamlit will run on
EXPOSE 7860

# Create a start script to run both FastAPI and Streamlit
# We run FastAPI on 8000 and Streamlit on 7860
RUN echo '#!/bin/bash\n\
python -m uvicorn main:app --host 0.0.0.0 --port 8000 &\n\
python -m streamlit run streamlit_app.py --server.port 7860 --server.address 0.0.0.0\n\
' > start.sh && chmod +x start.sh

# Run the start script
CMD ["./start.sh"]
