from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_ROOT = PROJECT_ROOT / "Website"
PAGES = {
    "install": WEBSITE_ROOT / "install" / "index.html",
    "integrations": WEBSITE_ROOT / "integrations" / "index.html",
    "enterprise": WEBSITE_ROOT / "enterprise" / "index.html",
    "blog": WEBSITE_ROOT / "blog" / "index.html",
}


class WebsiteHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        relative_path = unquote(urlsplit(path).path).lstrip("/")
        route = relative_path.rstrip("/")

        if relative_path in ("", "index.html"):
            target = WEBSITE_ROOT / "index.html"
        elif route in PAGES:
            target = PAGES[route]
        elif relative_path.startswith("dist/"):
            target = PROJECT_ROOT / relative_path
        elif relative_path == "LICENSE":
            target = PROJECT_ROOT / "LICENSE"
        else:
            target = WEBSITE_ROOT / relative_path

        resolved_target = target.resolve()
        if not resolved_target.is_relative_to(PROJECT_ROOT):
            return str(WEBSITE_ROOT / "index.html")
        return str(resolved_target)


if __name__ == "__main__":
    address = ("127.0.0.1", 8765)
    print(f"Smart File Organizer website: http://{address[0]}:{address[1]}/")
    ThreadingHTTPServer(address, WebsiteHandler).serve_forever()
