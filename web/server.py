"""
web/server.py
-------------
Entry point for the pdf2TeX web server.

Usage:
    python web/server.py
    python web/server.py --port 8080
"""

import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="pdf2TeX web server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    print(f"\n  pdf2TeX web UI")
    print(f"  Running at  http://{args.host}:{args.port}")
    print(f"  Press Ctrl+C to stop\n")

    uvicorn.run(
        "web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
