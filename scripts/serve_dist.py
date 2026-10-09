"""Serve the production frontend build and check it end to end against the API.

`npm run build` produces static files in `frontend/dist`. This script mounts that
directory on the same origin as the API and walks the built app the way a
browser would: fetch the HTML shell, follow the SPA fallback for a deep link,
and confirm the API answers through the same origin.

    cd frontend
    npm run build
    python ../scripts/serve_dist.py

It prints the URL to open and serves until interrupted.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "frontend" / "dist"
sys.path.insert(0, str(ROOT / "backend"))

if not DIST.exists():
    raise SystemExit(
        f"{DIST} does not exist.\nRun `npm install && npm run build` in frontend/ first."
    )


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="medbill-dist-"))
    # Point the app at a throwaway database so serving the build cannot touch
    # development data.
    os.environ.update(
        {
            "MEDBILL_DATABASE_URL": f"sqlite:///{(workdir / 'serve.db').as_posix()}",
            "MEDBILL_STORAGE_DIR": str(workdir / "uploads"),
            "MEDBILL_RATE_LIMIT_ENABLED": "false",
        }
    )

    import httpx
    import uvicorn
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse, JSONResponse

    from app.main import create_app

    app = create_app()
    assets = DIST / "assets"

    # Hashed asset filenames are safe to cache aggressively; index.html must not be.
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Serve static files, falling back to the SPA shell for client routes."""
        if full_path.startswith("api/"):
            return JSONResponse({"error": {"code": "not_found", "message": "Unknown endpoint."}}, 404)
        candidate = DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")

    host, port = "127.0.0.1", 8080
    print(f"\n  MedBill Lens - full stack")
    print(f"  http://{host}:{port}\n")
    print("  Frontend and API share an origin, so this build needs no CORS setup.")
    print("  Press Ctrl+C to stop.\n")

    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)

    import threading

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        thread.join()
    except KeyboardInterrupt:
        print("\nstopping")
        server.should_exit = True

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
