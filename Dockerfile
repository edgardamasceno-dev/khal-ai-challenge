# Imagem do backend (API REST legada). Instala o projeto a partir do
# pyproject (fonte unica de deps) e roda o uvicorn.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Libs de sistema do WeasyPrint (render da fatura A4 — SPEC-008/ADR-0009).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 libgdk-pixbuf-2.0-0 \
    fonts-dejavu-core fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY pyproject.toml ./
COPY src ./src
COPY kb ./kb
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "src.interfaces.rest.app:app", "--host", "0.0.0.0", "--port", "8000"]
