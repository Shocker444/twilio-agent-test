# Use the official Python image
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install --no-cache-dir uv

# Copy the uv dependency files
COPY pyproject.toml uv.lock ./

# Install project dependencies using uv
RUN uv sync --frozen --no-install-project

# Copy the rest of the application
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Ensure the virtual environment is in PATH
ENV PATH="/app/.venv/bin:$PATH"

# Command to run the application
CMD ["python", "main.py"]
