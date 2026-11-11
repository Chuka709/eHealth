"""Private object storage for uploaded documents (Phase 3; docs/04 §3, Q49).

Only sealed bytes reach it (documents/service.py encrypts with the KEK envelope first), so
the bucket never holds a readable health record. Keys are `{patient_id}/{document_id}/...`.
The S3 client is synchronous (boto3): calls run in a worker thread.
"""

from functools import lru_cache
from typing import TYPE_CHECKING, Protocol

from anyio import to_thread

from labtrack.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


class StorageError(Exception):
    """The store could not be reached or refused (never carries a key or content)."""


class S3ObjectStore:
    def __init__(self, client: "S3Client", bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def put(self, key: str, data: bytes) -> None:
        def run() -> None:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType="application/octet-stream"
            )

        await self._call(run)

    async def get(self, key: str) -> bytes:
        def run() -> bytes:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

        return await self._call(run)

    async def delete(self, key: str) -> None:
        def run() -> None:
            self._client.delete_object(Bucket=self._bucket, Key=key)

        await self._call(run)

    def ensure_bucket(self) -> None:
        """Dev/test: the bucket is created on first use (production provisions it)."""
        from botocore.exceptions import ClientError  # noqa: PLC0415

        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    @staticmethod
    async def _call[T](run: "_Run[T]") -> T:
        from botocore.exceptions import BotoCoreError, ClientError  # noqa: PLC0415

        try:
            return await to_thread.run_sync(run)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError from exc


class _Run[T](Protocol):
    def __call__(self) -> T: ...


class MemoryObjectStore:
    """Tests only: a dict in this process."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    async def get(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError as exc:
            raise StorageError from exc

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


@lru_cache
def get_store() -> ObjectStore:
    settings = get_settings()
    if settings.s3_endpoint_url is None:
        if settings.environment not in {"dev", "test"}:
            raise RuntimeError("S3_ENDPOINT_URL is required outside dev/test")
        return MemoryObjectStore()
    import boto3  # noqa: PLC0415
    from botocore.config import Config  # noqa: PLC0415

    if settings.s3_access_key is None or settings.s3_secret_key is None:
        raise RuntimeError("S3_ACCESS_KEY and S3_SECRET_KEY are required")
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=30,
        ),
    )
    store = S3ObjectStore(client, settings.s3_bucket)
    if settings.environment in {"dev", "test"}:
        store.ensure_bucket()
    return store
