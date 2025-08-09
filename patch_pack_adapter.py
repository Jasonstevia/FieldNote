
from typing import Any, Dict, List, Tuple, Optional
import json, zipfile, io, os
from cms_base import CMSClient

class PatchPackAdapter(CMSClient):
    """No creds. Produces a ZIP with patches & instructions."""
    def __init__(self, creds):
        self.creds = creds or {}
    def _zip_bytes(self, files: Dict[str, str]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            for path, content in files.items():
                z.writestr(path, content)
        return buf.getvalue()
    def update_page_meta(self, page_id_or_path: str, title=None, description=None, canonical=None):
        files = {"instructions.md": "Edit head tags accordingly."}
        return {"ok": True, "zip": True, "bytes_len": len(self._zip_bytes(files))}
    def inject_json_ld(self, page_id_or_path: str, json_ld):
        files = {"instructions.md": "Paste JSON-LD into head."}
        return {"ok": True, "zip": True, "bytes_len": len(self._zip_bytes(files))}
    def create_post(self, collection_or_path: str, title: str, html: str, slug: str=None, date: str=None, meta=None):
        files = {f"{slug or 'post'}.html": html, "instructions.md": "Upload this file."}
        return {"ok": True, "zip": True, "bytes_len": len(self._zip_bytes(files))}
    def set_redirects(self, redirects):
        files = {"redirects.txt": "\n".join([f"{a} -> {b} {c}" for a,b,c in redirects])}
        return {"ok": True, "zip": True, "bytes_len": len(self._zip_bytes(files))}
