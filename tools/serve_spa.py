import http.server, os, sys
ROOT = sys.argv[1]; PORT = int(sys.argv[2])
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=ROOT, **kw)
    def do_GET(self):
        path = self.path.split("?")[0]
        full = os.path.join(ROOT, path.lstrip("/"))
        if path not in ("/", "") and not os.path.isfile(full):
            self.path = "/index.html"
        return super().do_GET()
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
