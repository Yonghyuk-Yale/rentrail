"""Start Rentrail:  python run.py   then open the address it prints (normally http://127.0.0.1:8460)

Options: --port 8470 (a specific port), --no-browser (do not open a browser tab).
If the default port is busy, the next free port is used automatically.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) != 0


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles (e.g. cp949) cannot print every character
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if sys.version_info < (3, 10):
        sys.exit(f"Rentrail needs Python 3.10 or newer (this is {sys.version.split()[0]}).")
    try:
        import config
        import uvicorn
        import fastapi, pydantic_ai, cv2, pdfplumber, cryptography  # noqa: F401,E401  (fail early with a clear message)
    except ImportError as exc:
        venv_py = r".venv\Scripts\python" if sys.platform == "win32" else ".venv/bin/python"
        sys.exit(f"Missing package ({exc.name}). Install first:\n    {venv_py} -m pip install -r requirements.txt\n"
                 f"then start with:\n    {venv_py} run.py")

    ap = argparse.ArgumentParser(description="Run the Rentrail web app")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    port = args.port or config.PORT
    if args.port is None:  # default port busy (e.g. another student's app)? take the next free one
        for candidate in range(port, port + 20):
            if _port_free(args.host, candidate):
                port = candidate
                break

    status = config.key_status()
    print("Rentrail - tenant-side lease agent (Connecticut)")
    print(f"  model: {status['model']} via Portkey")
    print(f"  PORTKEY_API_KEY found: {status['portkey_key_found']}  (.env checked: {status['env_files'] or 'none, using environment'})")
    if not status["portkey_key_found"]:
        print("  ! No key: the demo data still opens, but new AI runs will show an error until a .env is added.")
    url = f"http://{args.host}:{port}"
    print(f"\n  Rentrail is starting at  {url}   <- open this in your browser (Ctrl+C to stop)\n")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run("app:app", host=args.host, port=port, app_dir=str(ROOT / "backend"), log_level="warning")


if __name__ == "__main__":
    main()
