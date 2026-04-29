# Use Python 3.11-slim
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Install basic system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and set permissions early
RUN useradd -m -u 1000 user && \
    chown -R user:user /app

USER user
ENV PATH="/home/user/.local/bin:$PATH"

# Copy setup files first for caching
COPY --chown=user requirements.txt setup.py pyproject.toml* README.md* ./

# Install dependencies
# We ignore the -e . if it fails or just install requirements normally
RUN pip install --no-cache-dir --user -r requirements.txt || \
    pip install --no-cache-dir --user $(grep -v '^-e' requirements.txt)

# Copy the rest of the application
COPY --chown=user . .

# Expose port 7860
EXPOSE 7860

# Create a start script
RUN echo '#!/bin/bash\n\
python -m uvicorn main:app --host 0.0.0.0 --port 8000 &\n\
python -m streamlit run streamlit_app.py --server.port 7860 --server.address 0.0.0.0\n\
' > start.sh && chmod +x start.sh

# Run the start script
CMD ["./start.sh"]
