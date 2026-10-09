"""Storage access: Cloudflare R2 through boto3, or a local folder for tests (helper module).

Run command: none. This is a helper module, it is imported by upload_r2.py,
finalize_release.py and promote_release.py.

Keys come from environment variables, never from code:
R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_STAGING_BUCKET.
If ABF_LOCAL_STORE is set, a folder <ABF_LOCAL_STORE>/<bucket>/ is used instead
of R2 (for tests without network).
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Iterator

from common import content_headers, sha256_file

log = logging.getLogger("publish.r2")

RETRIES = 4


class StoreError(RuntimeError):
    """Storage problem (missing variable, failed request)."""


def _need(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise StoreError(f"environment variable {name} is not set (see SPEC_META section 8, step 6)")
    return value


def _retry(fn, what: str):  # noqa: ANN001, ANN202
    delay = 1.0
    for attempt in range(1, RETRIES + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - boto3 raises many types
            if attempt == RETRIES:
                raise StoreError(f"{what} failed after {RETRIES} tries: {exc}") from exc
            log.warning("%s failed (%s), retry %d/%d", what, exc, attempt, RETRIES)
            time.sleep(delay)
            delay *= 2


class S3Store:
    """One R2 bucket."""

    def __init__(self, bucket: str) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        account = _need("R2_ACCOUNT_ID")
        kwargs: dict[str, Any] = {"retries": {"max_attempts": 3, "mode": "standard"}, "signature_version": "s3v4"}
        try:
            cfg = Config(request_checksum_calculation="when_required",
                         response_checksum_validation="when_required", **kwargs)
        except TypeError:  # older botocore has no such options
            cfg = Config(**kwargs)
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
            aws_access_key_id=_need("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=_need("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
            config=cfg,
        )

    def head(self, key: str) -> dict[str, Any] | None:
        from botocore.exceptions import ClientError

        try:
            r = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise StoreError(f"head {key}: {exc}") from exc
        return {"bytes": int(r["ContentLength"]), "sha256": (r.get("Metadata") or {}).get("sha256"), "etag": r.get("ETag")}

    def list(self, prefix: str) -> Iterator[dict[str, Any]]:
        token = None
        while True:
            kw: dict[str, Any] = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                kw["ContinuationToken"] = token
            r = _retry(lambda: self.client.list_objects_v2(**kw), f"list {prefix}")
            for item in r.get("Contents", []):
                yield {"key": item["Key"], "bytes": int(item["Size"])}
            if not r.get("IsTruncated"):
                return
            token = r["NextContinuationToken"]

    def put_file(self, path: Path, key: str, sha256: str | None = None) -> None:
        headers = content_headers(key)
        extra = {"ContentType": headers["Content-Type"], "CacheControl": headers["Cache-Control"],
                 "Metadata": {"sha256": sha256 or sha256_file(path)}}
        if "Content-Disposition" in headers:
            extra["ContentDisposition"] = headers["Content-Disposition"]
        _retry(lambda: self.client.upload_file(str(path), self.bucket, key, ExtraArgs=extra), f"upload {key}")

    def put_bytes(self, data: bytes, key: str) -> None:
        headers = content_headers(key)
        kw = {"Bucket": self.bucket, "Key": key, "Body": data, "ContentType": headers["Content-Type"],
              "CacheControl": headers["Cache-Control"]}
        _retry(lambda: self.client.put_object(**kw), f"put {key}")

    def get_file(self, key: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _retry(lambda: self.client.download_file(self.bucket, key, str(dest)), f"download {key}")

    def get_bytes(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise StoreError(f"get {key}: {exc}") from exc

    def delete_prefix(self, prefix: str) -> int:
        keys = [i["key"] for i in self.list(prefix)]
        for i in range(0, len(keys), 1000):
            batch = [{"Key": k} for k in keys[i:i + 1000]]
            _retry(lambda: self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": batch}), "delete")
        return len(keys)


class LocalStore:
    """A folder that behaves like a bucket (tests)."""

    def __init__(self, root: Path) -> None:
        self.bucket = root.name
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str) -> Path:
        return self.root / key

    def head(self, key: str) -> dict[str, Any] | None:
        p = self._p(key)
        if not p.is_file():
            return None
        side = p.with_name(p.name + ".sha256")
        return {"bytes": p.stat().st_size, "sha256": side.read_text().strip() if side.exists() else None, "etag": None}

    def list(self, prefix: str) -> Iterator[dict[str, Any]]:
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and not p.name.endswith(".sha256"):
                key = p.relative_to(self.root).as_posix()
                if key.startswith(prefix):
                    yield {"key": key, "bytes": p.stat().st_size}

    def put_file(self, path: Path, key: str, sha256: str | None = None) -> None:
        dst = self._p(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dst)
        dst.with_name(dst.name + ".sha256").write_text(sha256 or sha256_file(path))

    def put_bytes(self, data: bytes, key: str) -> None:
        dst = self._p(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)

    def get_file(self, key: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._p(key), dest)

    def get_bytes(self, key: str) -> bytes | None:
        p = self._p(key)
        return p.read_bytes() if p.is_file() else None

    def delete_prefix(self, prefix: str) -> int:
        n = 0
        for item in list(self.list(prefix)):
            p = self._p(item["key"])
            p.unlink()
            side = p.with_name(p.name + ".sha256")
            if side.exists():
                side.unlink()
            n += 1
        return n


def open_store(bucket_env: str) -> S3Store | LocalStore:
    """Store of the bucket named in the environment variable `bucket_env`."""
    bucket = _need(bucket_env)
    local = os.environ.get("ABF_LOCAL_STORE", "").strip()
    if local:
        return LocalStore(Path(local) / bucket)
    return S3Store(bucket)
