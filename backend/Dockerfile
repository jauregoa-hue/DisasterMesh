FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./

# Docker Scout flagged pip 25.0.1. This requires a patched pip release.
# Base-image OS vulnerabilities still depend on upstream Debian/Python patches.
RUN python -m pip install --no-cache-dir --upgrade pip "setuptools>=84.1.0" \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --system appgroup \
    && useradd --system --gid appgroup appuser

COPY --chown=appuser:appgroup app ./app

USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
