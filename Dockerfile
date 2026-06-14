# --- Build Stage (Frontend) ---
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Run Stage (Backend) ---
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies (needed for some python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# First install torch CPU specifically as requested in requirements.txt
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy built frontend from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=8000

# Run the server
# Use the PORT env var provided by Render
CMD uvicorn backend.server.app:app --host 0.0.0.0 --port $PORT
