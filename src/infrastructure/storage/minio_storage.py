"""Adapter de object storage em MinIO (S3-compatível). Implementa ObjectStorage.

URL estável via proxy do gateway (`public_base_url`/{key}); presigned via MinIO.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json


class MinioObjectStorage:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        public_base_url: str,
        secure: bool = False,
    ) -> None:
        from minio import Minio

        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self._bucket = bucket
        self._public_base = public_base_url.rstrip("/")
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
        # Leitura anônima dos objetos (o gateway faz proxy sem credencial).
        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow", "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{self._bucket}/*"],
            }],
        }
        with contextlib.suppress(Exception):  # best-effort (idempotente)
            self._client.set_bucket_policy(self._bucket, json.dumps(policy))

    def exists(self, key: str) -> bool:
        from minio.error import S3Error

        try:
            self._client.stat_object(self._bucket, key)
            return True
        except S3Error:
            return False

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            self._bucket, key, io.BytesIO(data), length=len(data), content_type=content_type
        )

    def public_url(self, key: str) -> str:
        return f"{self._public_base}/{key}"

    def presigned_url(self, key: str, expires_seconds: int) -> str:
        return self._client.presigned_get_object(
            self._bucket, key, expires=dt.timedelta(seconds=expires_seconds)
        )
