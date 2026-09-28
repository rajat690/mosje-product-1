"""Small httpx client for the MoSJE API. Reads API_BASE_URL (or API_HOST) and API_KEY from the env."""
from __future__ import annotations

import os

import httpx


def candidate_base_urls() -> list[str]:
    """API_BASE_URL wins. On Render the blueprint also passes API_HOST (the API service's host name);
    free web services cannot receive private-network traffic, so we try its public onrender.com URL."""
    urls = []
    base = os.environ.get("API_BASE_URL", "").strip().rstrip("/")
    if base:
        urls.append(base if base.startswith("http") else "https://" + base)
    host = os.environ.get("API_HOST", "").strip()
    if host:
        urls.append(f"https://{host}" if "." in host else f"https://{host}.onrender.com")
        port = os.environ.get("API_PORT", "").strip()
        if port:
            urls.append(f"http://{host}:{port}")
    if not urls:
        urls.append("http://localhost:8000")
    return urls


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, payload=None):
        super().__init__(message)
        self.status = status
        self.payload = payload           # parsed JSON "detail" of the error, if any


def _error(method: str, path: str, r: httpx.Response) -> ApiError:
    try:
        payload = r.json().get("detail")
    except Exception:  # noqa: BLE001
        payload = None
    return ApiError(f"{method} {path} -> {r.status_code}: {r.text[:300]}", r.status_code, payload)


class MosjeApi:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 90.0,
                 transport=None):
        self.api_key = api_key if api_key is not None else os.environ.get("API_KEY", "")
        self.timeout = timeout
        self.transport = transport
        self.base_url = base_url or self._discover()

    def _client(self, base):
        kw = {"base_url": base, "timeout": self.timeout, "headers": {"X-API-Key": self.api_key}}
        if self.transport is not None:
            kw["transport"] = self.transport
        return httpx.Client(**kw)

    def _discover(self) -> str:
        cands = candidate_base_urls()
        for base in cands:
            try:
                with self._client(base) as c:
                    if c.get("/health").status_code == 200:
                        return base
            except httpx.HTTPError:
                continue
        return cands[0]

    def get(self, path: str, **params):
        with self._client(self.base_url) as c:
            r = c.get(path, params={k: v for k, v in params.items() if v is not None})
        if r.status_code >= 400:
            raise _error("GET", path, r)
        return r.json()

    def post(self, path: str, **params):
        with self._client(self.base_url) as c:
            r = c.post(path, params={k: v for k, v in params.items() if v is not None})
        if r.status_code >= 400:
            raise _error("POST", path, r)
        return r.json()

    def upload(self, path: str, filename: str, content, timeout: float = 900.0, **params):
        """POST a file as multipart field 'file' (content: bytes or a binary file object)."""
        with self._client(self.base_url) as c:
            r = c.post(path, params={k: v for k, v in params.items() if v is not None},
                       files={"file": (filename, content, "application/octet-stream")}, timeout=timeout)
        if r.status_code >= 400:
            raise _error("POST", path, r)
        return r.json()

    def get_all(self, path: str, page_size: int = 5000, **params) -> list[dict]:
        items, page = [], 1
        while True:
            d = self.get(path, page=page, page_size=page_size, **params)
            items.extend(d["items"])
            if len(items) >= d["total"] or not d["items"]:
                return items
            page += 1
