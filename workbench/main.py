from __future__ import annotations

import uvicorn

from .api import create_app

app = create_app()


def main() -> None:
    uvicorn.run("workbench.main:app", host="0.0.0.0", port=8090, reload=True)


if __name__ == "__main__":
    main()
