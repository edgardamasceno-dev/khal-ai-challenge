"""Teste de integração do MinioObjectStorage (SPEC-008) contra MinIO efêmero."""

from __future__ import annotations

import os
import uuid

import pytest

from src.infrastructure.storage.minio_storage import MinioObjectStorage

pytestmark = pytest.mark.skipif(
    not os.environ.get("MINIO_ENDPOINT"), reason="MINIO_ENDPOINT nao definido"
)


def _storage() -> MinioObjectStorage:
    return MinioObjectStorage(
        endpoint=os.environ["MINIO_ENDPOINT"],
        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        bucket=os.environ.get("MINIO_BUCKET", "faturas-test"),
        public_base_url="http://localhost/files",
        secure=False,
    )


def test_put_exists_e_urls() -> None:
    s = _storage()
    key = f"invoices/{uuid.uuid4()}.pdf"
    assert s.exists(key) is False
    s.put(key, b"%PDF-1.7 teste", "application/pdf")
    assert s.exists(key) is True
    assert s.public_url(key) == f"http://localhost/files/{key}"
    pre = s.presigned_url(key, 600)
    assert key in pre and "X-Amz" in pre  # presigned assinado


def test_idempotente_put_sobrescreve_sem_erro() -> None:
    s = _storage()
    key = f"invoices/{uuid.uuid4()}.pdf"
    s.put(key, b"a", "application/pdf")
    s.put(key, b"bb", "application/pdf")  # não deve falhar
    assert s.exists(key) is True
