"""Локальный просмотр статического демо (_site/) так, как его отдаёт GitHub Pages (с префиксом /Moto-site.io/).

    python scripts/preview_pages.py [порт]      → http://localhost:5174/Moto-site.io/
"""
from __future__ import annotations

import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "_site"
PREFIX = "/Moto-site.io"


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        if path.startswith(PREFIX):
            path = path[len(PREFIX):] or "/"
        return super().translate_path(path)

    def send_error(self, code, message=None, explain=None):
        page = ROOT / "404.html"
        if code == 404 and page.is_file():
            body = page.read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().send_error(code, message, explain)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5174
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(ROOT)))
    print(f"http://localhost:{port}{PREFIX}/")
    server.serve_forever()
