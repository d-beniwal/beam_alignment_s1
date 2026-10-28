"""Local web GUI (stdlib only): follows runs/<id>/events.jsonl live. Read-only - it never moves anything.
Run:  python -I gui.py [--port 8765]   then open http://localhost:8765"""
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from . import RUNS_DIR
import align_config as cfg



def _latest():
    f = RUNS_DIR / "CURRENT"
    return f.read_text().strip() if f.exists() else None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, body, ctype="application/json", code=200):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        rid = q.get("run") or _latest()
        if u.path == "/":
            return self._send((Path(__file__).parent / "gui.html").read_text(), "text/html; charset=utf-8")
        if u.path == "/api/config":
            return self._send({"pixel_um": cfg.PIXEL_UM, "tol_ab_px": cfg.TOL_AB_PX, "tol_c_px": cfg.TOL_C_PX,
                               "latest": _latest(), "runs": sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir()) if RUNS_DIR.exists() else []})
        if rid is None:
            return self._send({"events": [], "state": None})
        d = (RUNS_DIR / rid).resolve()
        if RUNS_DIR.resolve() not in d.parents:
            return self._send({"error": "bad run"}, code=400)
        if u.path == "/api/events":
            since = int(q.get("since", 0))
            evs = []
            ep = d / "events.jsonl"
            if ep.exists():
                for i, line in enumerate(open(ep)):
                    if i >= since and line.strip():
                        evs.append(json.loads(line))
            st = json.loads((d / "state.json").read_text()) if (d / "state.json").exists() else None
            return self._send({"run": rid, "events": evs, "state": st})
        if u.path.startswith("/runs/"):
            f = (RUNS_DIR / u.path[len("/runs/"):]).resolve()
            if RUNS_DIR.resolve() in f.parents and f.is_file():
                return self._send(f.read_bytes(), mimetypes.guess_type(str(f))[0] or "application/octet-stream")
        self._send({"error": "not found"}, code=404)


def serve(port=8765):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"alignment GUI on http://localhost:{port}  (runs dir: {RUNS_DIR})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
    serve(port)
