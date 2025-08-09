
import base64
import json
from typing import Any, Dict, List, Tuple, Optional
import requests
from cms_base import CMSClient

class WordPressAdapter(CMSClient):
    def __init__(self, creds: Dict[str, Any]):
        self.base = creds.get('site_url', '').rstrip('/')
        user = creds.get('user')
        app_pw = creds.get('password')
        if not (self.base and user and app_pw):
            raise ValueError("Missing WordPress creds: need site_url, user, password (Application Password)." )
        token = base64.b64encode(f"{user}:{app_pw}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

    def _post(self, path: str, data: Dict[str, Any]):
        url = f"{self.base}/wp-json/wp/v2{path}"
        r = requests.post(url, headers=self.headers, data=json.dumps(data), timeout=30)
        r.raise_for_status()
        return r.json()

    def _put(self, path: str, data: Dict[str, Any]):
        url = f"{self.base}/wp-json/wp/v2{path}"
        r = requests.post(url, headers=self.headers, data=json.dumps(data), timeout=30)  # WP uses POST for updates
        r.raise_for_status()
        return r.json()

    def update_page_meta(self, page_id_or_path: str, title: Optional[str]=None, description: Optional[str]=None, canonical: Optional[str]=None):
        # Assume page_id_or_path is a numeric ID for v1; path lookup could be added via REST search
        payload: Dict[str, Any] = {}
        if title: payload['title'] = title
        if description: payload['excerpt'] = description
        # Yoast-specific fields (must be exposed via REST in WP to persist)
        yoast_meta = {}
        if title: yoast_meta['_yoast_wpseo_title'] = title
        if description: yoast_meta['_yoast_wpseo_metadesc'] = description
        if yoast_meta:
            payload['meta'] = yoast_meta
        return self._put(f"/pages/{page_id_or_path}", payload)

    def inject_json_ld(self, page_id_or_path: str, json_ld: Dict[str, Any]):
        # Simple strategy: append a <script> tag to content
        script = f"<script type=\"application/ld+json\">{json.dumps(json_ld)}</script>"
        return self._put(f"/pages/{page_id_or_path}", {"content": {"raw": script}})

    def create_post(self, collection_or_path: str, title: str, html: str, slug: Optional[str]=None, date: Optional[str]=None, meta: Optional[Dict[str, Any]]=None):
        payload = {"title": title, "content": html, "status": "draft"}
        if slug: payload['slug'] = slug
        if date: payload['date'] = date
        if meta: payload['meta'] = meta
        return self._post("/posts", payload)

    def set_redirects(self, redirects: List[Tuple[str, str, int]]):
        # Requires a redirects plugin or custom endpoint; return a stub for now
        return {"ok": False, "message": "Redirects require a plugin or custom endpoint."}
