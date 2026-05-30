# Imagem do backend (API REST legada). Instala o projeto a partir do
# pyproject (fonte unica de deps) e roda o uvicorn.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "src.interfaces.rest.app:app", "--host", "0.0.0.0", "--port", "8000"]
