FROM python:3.11-slim

# Create non-root user.
RUN groupadd -r appuser && useradd -r -g appuser -m appuser

WORKDIR /app

# Copy and install dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project.
COPY . .

# Set ownership for non-root run.
RUN chown -R appuser:appuser /app

# Switch to non-root user.
USER appuser

ARG PORT=8000
ENV PORT=${PORT}
ENV PYTHONUNBUFFERED=1

EXPOSE ${PORT}

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --no-access-log