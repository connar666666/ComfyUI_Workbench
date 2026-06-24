from __future__ import annotations

from workbench.config import load_settings
from workbench.db import initialize_db


def main() -> None:
    settings = load_settings()
    initialize_db(settings.db_path, settings.default_user, settings.default_role)
    print(f"initialized workbench database: {settings.db_path}")


if __name__ == "__main__":
    main()
