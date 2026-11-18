"""Local web interface: paste messages in the browser, click Run.
Runs on this laptop only (127.0.0.1). The API key never leaves Python.
Every Run calls the same process() as the command line, and the trace still prints here."""
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from engine import state
from ui import report

LOCK = threading.Lock()  # one run at a time, like the command line


def serve(process, port=None):
    port = int(port or os.getenv("UI_PORT", "8000"))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the terminal for the trace
            pass

        def _send(self, code, body, ctype):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.split("?")[0] not in ("/", "/index.html"):
                return self._send(404, "not found", "text/plain")
            paths = report.write_all(state.load())
            with open(paths["html"], encoding="utf-8") as fh:
                self._send(200, fh.read(), "text/html; charset=utf-8")

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                if self.path == "/run":
                    text = body.get("text") or ""
                    if not text.strip():
                        return self._send(400, json.dumps({"error": "No message text."}), "application/json")
                    src = (body.get("src") or "pasted text").strip()[:80]
                    with LOCK:
                        res = process(text, src)
                    res.pop("paths", None)
                    return self._send(200, json.dumps(res), "application/json")
                if self.path == "/reset":
                    with LOCK:
                        state.reset()
                        report.write_all(state.load())
                    print("\nState cleared from the web interface. The next run will be a full run.")
                    return self._send(200, json.dumps({"ok": True}), "application/json")
                self._send(404, json.dumps({"error": "not found"}), "application/json")
            except Exception as e:
                self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}), "application/json")

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    from engine.llm import key_hint
    print(f"Web interface running at {url}  (Ctrl+C to stop). The trace prints here.")
    print(f"Using model {os.getenv('LLM_MODEL')} with API key ending {key_hint()} (from .env)")
    if os.getenv("OPEN_BROWSER", "1") != "0":
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
