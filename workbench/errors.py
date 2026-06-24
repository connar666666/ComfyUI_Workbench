from __future__ import annotations


class WorkbenchError(Exception):
    status_code = 400
    code = "workbench_error"


class NotFoundError(WorkbenchError):
    status_code = 404
    code = "not_found"


class PermissionDeniedError(WorkbenchError):
    status_code = 403
    code = "permission_denied"


class ValidationError(WorkbenchError):
    status_code = 400
    code = "validation_error"


class ConflictError(WorkbenchError):
    status_code = 409
    code = "conflict"
