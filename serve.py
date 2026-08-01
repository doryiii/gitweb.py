#!/usr/bin/env python3
"""Standalone dev server for gitweb.py.

Serves the gitweb.py CGI script over HTTP so you can browse a directory of
git repositories in a browser without setting up a full webserver. It reuses
the CGI script verbatim -- one `python gitweb.py` subprocess per request -- so
what you see matches real CGI behaviour exactly.

This is a *development* server: no caching, no HTTPS, one process per request.
Do not use it in production.

Usage:
  python serve.py --root /path/to/repos
  python serve.py --root /path/to/repos --port 8000 --bind 127.0.0.1
"""
import argparse
import mimetypes
import os
import sys
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
GITWEB_PY = SCRIPT_DIR / "gitweb.py"
STATIC_DIR = SCRIPT_DIR / "static"

# PROJECT_ROOT for gitweb.py; set by create_server()/main() and read by the
# handler. Module-level so tests can point a server at a temp repo.
ROOT = os.getcwd()


class Handler(BaseHTTPRequestHandler):
  """Routes /static/* to files, everything else to the gitweb.py CGI."""

  # Quiet, prefixed logging (one line per request to stderr).
  def log_message(self, fmt, *args):
    sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

  def do_GET(self):
    parsed = urllib.parse.urlsplit(self.path)
    path = parsed.path
    query = parsed.query
    if path == "/static" or path.startswith("/static/"):
      return self._serve_static(path[len("/static/"):])
    return self._run_cgi(path, query)

  # --- static files -------------------------------------------------------

  def _serve_static(self, rel):
    rel = urllib.parse.unquote(rel)
    # Path-traversal guard: the resolved target must stay inside STATIC_DIR.
    try:
      target = (STATIC_DIR / rel).resolve()
      target.relative_to(STATIC_DIR.resolve())
    except ValueError:
      self.send_error(403, "Forbidden")
      return
    if not target.is_file():
      self.send_error(404, "Not Found")
      return
    data = target.read_bytes()
    ctype, _ = mimetypes.guess_type(target.name)
    self.send_response(200)
    self.send_header("Content-Type", ctype or "application/octet-stream")
    self.send_header("Content-Length", str(len(data)))
    self.end_headers()
    self.wfile.write(data)

  # --- CGI relay ----------------------------------------------------------

  def _run_cgi(self, path, query):
    env = os.environ.copy()
    env["GITWEB_PROJECTROOT"] = ROOT
    # SCRIPT_NAME="" makes href() emit root-relative URLs (/proj.git/log).
    env["SCRIPT_NAME"] = ""
    env["PATH_INFO"] = path
    env["QUERY_STRING"] = query
    env["REQUEST_METHOD"] = "GET"
    env["SERVER_NAME"] = self.server.server_address[0]
    env["SERVER_PORT"] = str(self.server.server_address[1])
    # Forward request headers as CGI HTTP_* vars (the CGI 1.1 convention:
    # uppercase, '-' -> '_', 'HTTP_' prefix). This is what lets gitweb.py do
    # content negotiation on Accept -- without it every request looks like it
    # came from a non-XHTML client and the page is served as text/html,
    # leaking the internal DTD subset's ']>' as visible text.
    for key, val in self.headers.items():
      cgi_key = "HTTP_" + key.upper().replace("-", "_")
      env[cgi_key] = val

    try:
      result = subprocess.run([sys.executable, str(GITWEB_PY)], env=env,
                              capture_output=True)
    except Exception as exc:  # pragma: no cover - spawn failure
      self.send_error(500, f"CGI spawn failed: {exc}")
      return

    if result.returncode != 0 or not result.stdout:
      detail = result.stderr.decode("utf-8", "replace").strip()[:500]
      self.send_error(500, "gitweb.py failed", detail)
      return

    self._send_cgi_output(result.stdout)

  def _send_cgi_output(self, out):
    # CGI output = header lines, a blank line, then the body. gitweb.py uses
    # print() (LF), so split on the first b"\n\n". The body may be binary
    # (snapshots write to sys.stdout.buffer), so keep everything as bytes.
    sep = out.find(b"\n\n")
    if sep == -1:
      header_blob, body = out, b""
    else:
      header_blob, body = out[:sep], out[sep + 2:]

    status = 200
    message = "OK"
    headers = []
    for line in header_blob.split(b"\n"):
      if not line:
        continue
      try:
        line_s = line.decode("latin-1")
      except UnicodeDecodeError:
        continue
      if ":" not in line_s:
        continue
      key, _, val = line_s.partition(":")
      key, val = key.strip(), val.strip()
      if key.lower() == "status":
        parts = val.split(None, 1)
        try:
          status = int(parts[0])
        except ValueError:
          continue
        message = parts[1] if len(parts) > 1 else ""
      else:
        headers.append((key, val))

    self.send_response(status, message)
    for key, val in headers:
      self.send_header(key, val)
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    if body:
      self.wfile.write(body)


def create_server(root, bind="127.0.0.1", port=8000):
  """Build a ThreadingHTTPServer for *root* (a PROJECT_ROOT path).

  port=0 lets the OS choose a free port (used by tests); the chosen port is
  on the returned server's server_address."""
  global ROOT
  ROOT = str(Path(root).resolve())
  server = ThreadingHTTPServer((bind, port), Handler)
  server.daemon_threads = True
  return server


def main():
  parser = argparse.ArgumentParser(
      description="Development web server for gitweb.py.")
  parser.add_argument("--root", required=True,
                      help="Directory of git repositories to serve "
                           "(GITWEB_PROJECTROOT).")
  parser.add_argument("--bind", "-b", default="127.0.0.1",
                      help="Interface to bind to (default: 127.0.0.1).")
  parser.add_argument("--port", "-p", type=int, default=8000,
                      help="Port to listen on (default: 8000).")
  args = parser.parse_args()

  server = create_server(args.root, args.bind, args.port)
  host, port = server.server_address
  print(f"Serving repos from {ROOT}")
  print(f"  http://{host}:{port}/  (Ctrl-C to stop)", flush=True)
  try:
    server.serve_forever()
  except KeyboardInterrupt:
    print("\nStopping.")
  finally:
    server.server_close()


if __name__ == "__main__":
  main()
