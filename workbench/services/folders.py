from __future__ import annotations

from ..repositories import WorkbenchRepository


class FolderService:
    def __init__(self, repo: WorkbenchRepository):
        self.repo = repo
