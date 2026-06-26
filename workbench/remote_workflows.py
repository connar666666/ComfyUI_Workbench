from __future__ import annotations

from typing import Any, BinaryIO
from urllib.parse import quote

import httpx

from .errors import ServiceUnavailableError, ValidationError


class RemoteWorkflowClient:
    def __init__(
        self,
        base_url: str | None,
        token: str | None = None,
        client: httpx.Client | None = None,
    ):
        if not base_url:
            raise ServiceUnavailableError("ZEALMAN_BASE_URL is not configured")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = client or httpx.Client(timeout=30, trust_env=False)

    def list_workflows(self) -> list[dict[str, Any]]:
        payload = self._request_json("GET", "/api/workflow/list")
        workflows = payload.get("workflows", [])
        if not isinstance(workflows, list):
            raise ValidationError("Remote workflow list returned an invalid payload")
        return workflows

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        payload = self._request_json("GET", f"/api/workflow/config/{quote(workflow_id, safe='')}")
        return {
            "workflow_id": workflow_id,
            "workflow_template": payload.get("workflow_template", {}),
            "api_config": payload.get("api_config", {}),
        }

    def run_workflow(self, workflow_id: str, input_values: dict[str, Any]) -> dict[str, Any]:
        payload = self._request_json(
            "POST",
            "/api/workflow/generate",
            json={"workflow_id": workflow_id, "input_values": input_values},
        )
        prompt_id = payload.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ValidationError("Remote workflow run did not return a prompt_id")
        return {"prompt_id": prompt_id}

    def get_result(self, prompt_id: str) -> dict[str, Any]:
        payload = self._request_json(
            "GET",
            "/api/workflow/result",
            params={"prompt_id": prompt_id},
        )
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise ValidationError("Remote workflow result returned an invalid payload")

        normalized_results: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            normalized_item = dict(item)
            if isinstance(url, str) and url.startswith("/"):
                normalized_item["download_url"] = f"{self.base_url}{url}"
            elif isinstance(url, str):
                normalized_item["download_url"] = url
            normalized_results.append(normalized_item)

        return {
            "prompt_id": payload.get("prompt_id", prompt_id),
            "pending": bool(payload.get("pending", False)),
            "results": normalized_results,
        }

    def upload_file(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str | None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        payload = self._request_json(
            "POST",
            "/api/comfy/upload/file",
            files={"file": (filename, file, content_type or "application/octet-stream")},
            data={"overwrite": str(overwrite).lower()},
        )
        name = payload.get("name")
        if not isinstance(name, str) or not name:
            raise ValidationError("Remote upload did not return a file name")
        return payload

    def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = kwargs.pop("headers", {})
        headers.update(self._auth_headers())
        try:
            response = self.client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_message(exc.response)
            if exc.response.status_code in {401, 403}:
                raise ServiceUnavailableError(detail or "Remote workflow API rejected the configured token") from exc
            if exc.response.status_code == 404:
                raise ValidationError(detail or "Remote workflow resource was not found") from exc
            raise ServiceUnavailableError(detail or "Remote workflow API request failed") from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError("Remote workflow API is unavailable") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValidationError("Remote workflow API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValidationError("Remote workflow API returned an invalid payload")
        return payload

    def _auth_headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip() or None
        if isinstance(payload, dict):
            for key in ("message", "detail", "error"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return None
