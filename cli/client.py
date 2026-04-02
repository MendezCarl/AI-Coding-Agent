from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class ApiResult:
    ok: bool
    status_code: int
    payload: dict


class ApiClient:
    def __init__(self, base_url: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get(self, path: str) -> ApiResult:
        return self._request("GET", path, None)

    def post(self, path: str, payload: dict) -> ApiResult:
        return self._request("POST", path, payload)

    def _request(self, method: str, path: str, payload: dict | None) -> ApiResult:
        url = f"{self.base_url}{path}"

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(method=method, url=url, json=payload)

            try:
                data = response.json()
                if not isinstance(data, dict):
                    data = {"status": "error", "error": "Non-object JSON response", "data": data}
            except ValueError:
                data = {
                    "status": "error",
                    "error": "Response was not valid JSON",
                    "raw": response.text,
                }

            return ApiResult(
                ok=200 <= response.status_code < 300,
                status_code=response.status_code,
                payload=data,
            )
        except httpx.RequestError as e:
            return ApiResult(
                ok=False,
                status_code=0,
                payload={"status": "error", "error": str(e)},
            )
