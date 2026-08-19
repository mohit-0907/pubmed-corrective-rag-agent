FROM python:3.11-slim

WORKDIR /app

# Installed before copying source so code changes don't invalidate this
# (usually the slowest) layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what api/main.py actually needs at runtime - not eval/, frontend/,
# or the data pipeline's raw-data output.
COPY agent/ agent/
COPY api/ api/
COPY data_pipeline/ data_pipeline/

RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
