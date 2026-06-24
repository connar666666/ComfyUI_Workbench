from __future__ import annotations

from typing import Any

import httpx


class ComfyUIQueueClient:
    def __init__(self, comfyui_url: str, client: httpx.Client | None = None):
        self.comfyui_url = comfyui_url.rstrip("/")
        self.client = client or httpx.Client(timeout=10)

    def fetch_queue(self) -> dict[str, list[dict[str, Any]]]:
        response = self.client.get(f"{self.comfyui_url}/queue")
        response.raise_for_status()
        payload = response.json()
        return {
            "running": self._normalize_entries(payload.get("queue_running", [])),
            "pending": self._normalize_entries(payload.get("queue_pending", [])),
        }

    @staticmethod
    def _normalize_entries(entries: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, entry in enumerate(entries):
            prompt_id = entry[0] if isinstance(entry, list) and entry else None
            normalized.append({
                "prompt_id": prompt_id,
                "queue_position": index,
                "raw": entry,
            })
        return normalized
