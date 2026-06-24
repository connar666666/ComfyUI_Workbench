from __future__ import annotations

from ..repositories import WorkbenchRepository


class VideoService:
    def __init__(self, repo: WorkbenchRepository):
        self.repo = repo
