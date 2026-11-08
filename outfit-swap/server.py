"""Outfit Swap: upload a photo of a person and change what they are wearing.

Run:  python server.py   then open http://localhost:8001
Needs an OpenAI API key in the OPENAI_API_KEY environment variable.
Uses only the Python standard library (no pip install needed).
"""

import base64
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "8001"))
API_BASE = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
MODEL = os.environ.get("OUTFIT_MODEL", "gpt-image-1")
MAX_UPLOAD = 15 * 1024 * 1024

# Requests that try to remove or reduce clothing are refused before any API call.
BLOCKED = re.compile(
    r"\b(nude|naked|topless|bottomless|undress|unclothed|nsfw|lingerie|underwear|"
    r"bra|panties|thong|see[- ]?through|sheer|transparent|strip|no clothes|bikini|"
    r"sexy|revealing)\b",
    re.I,
)


def build_prompt(outfit: str) -> str:
    return (
        "Edit this photo so the person is wearing: "
        f"{outfit}. "
        "Change only the clothing named; keep any other clothing they already wear "
        "unless the new item replaces it (a dress replaces both top and bottom). "
        "Keep the person's face, identity, hair, skin tone, body shape, pose, "
        "expression, hands, background, lighting and camera angle exactly the same. "
        "The new clothes should fit naturally with realistic fabric, folds and shadows. "
        "The person must remain fully and modestly clothed."
    )


def multipart(fields: dict, file_field: str, filename: str, file_bytes: bytes, mime: str):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'
        ).encode()
        + file_bytes
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def edit_image(image_bytes: bytes, mime: str, outfit: str) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "No OPENAI_API_KEY set. Get a key at platform.openai.com, then run "
            "'export OPENAI_API_KEY=your-key' (Windows: 'set OPENAI_API_KEY=your-key') "
            "and restart the server."
        )
    fields = {
        "model": MODEL,
        "prompt": build_prompt(outfit),
        "n": "1",
        "size": "auto",
        "quality": os.environ.get("OUTFIT_QUALITY", "medium"),
        "input_fidelity": "high",
    }
    ext = "png" if mime == "image/png" else "jpg"
    body, ctype = multipart(fields, "image", f"photo.{ext}", image_bytes, mime)
    req = urllib.request.Request(
        f"{API_BASE}/images/edits",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": ctype},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e)["error"]["message"]
        except Exception:
            msg = f"HTTP {e.code}"
        raise RuntimeError(f"Image service error: {msg}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach the image service: {e.reason}") from None
    return data["data"][0]["b64_json"]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE / "static"), **kwargs)

    def send_json(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/status":
            return self.send_json(
                200, {"ready": bool(os.environ.get("OPENAI_API_KEY")), "model": MODEL}
            )
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/swap":
            return self.send_json(404, {"error": "Not found"})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_UPLOAD * 2:
            return self.send_json(413, {"error": "Photo is too large (max about 15 MB)."})
        try:
            req = json.loads(self.rfile.read(length))
            outfit = str(req.get("outfit", "")).strip()[:300]
            m = re.match(r"^data:(image/(?:png|jpeg));base64,(.+)$", req.get("image", ""), re.S)
            if not m:
                return self.send_json(400, {"error": "Please upload a PNG or JPEG photo."})
            if not outfit:
                return self.send_json(400, {"error": "Pick at least one clothing item."})
            if BLOCKED.search(outfit):
                return self.send_json(
                    400, {"error": "This app only puts people in regular, fully clothed outfits."}
                )
            image_bytes = base64.b64decode(m.group(2))
            result = edit_image(image_bytes, m.group(1), outfit)
            return self.send_json(200, {"image": f"data:image/png;base64,{result}"})
        except RuntimeError as e:
            return self.send_json(502, {"error": str(e)})
        except Exception as e:  # keep the server alive on bad input
            return self.send_json(500, {"error": f"Something went wrong: {e}"})

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY is not set; the page will load but swaps will fail.")
    print(f"Outfit Swap running at http://localhost:{PORT}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
