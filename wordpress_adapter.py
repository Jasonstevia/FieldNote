
import base64
import json
from typing import Any, Dict, List, Tuple, Optional
from urllib.parse import urlparse
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

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None):
        url = f"{self.base}/wp-json/wp/v2{path}"
        r = requests.get(url, headers=self.headers, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

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

    def _canonical_path(self, url_or_path: str) -> str:
        parsed = urlparse(url_or_path)
        path = parsed.path if parsed.scheme else url_or_path
        path = "/" + path.lstrip("/")
        return path.rstrip("/") or "/"

    def _resolve_resource(self, page_id_or_path: str) -> Tuple[str, int, Dict[str, Any]]:
        if str(page_id_or_path).isdigit():
            numeric_id = int(page_id_or_path)
            for resource_type in ("pages", "posts"):
                try:
                    item = self._get(f"/{resource_type}/{numeric_id}", params={"context": "edit"})
                    return resource_type, numeric_id, item
                except requests.HTTPError:
                    continue
            raise ValueError(f"Could not find a WordPress page or post with ID {page_id_or_path}.")

        target_path = self._canonical_path(page_id_or_path)
        if target_path == "/":
            raise ValueError("Homepage updates require a WordPress ID; URL-based homepage lookup is not supported yet.")

        slug = target_path.split("/")[-1]
        for resource_type in ("pages", "posts"):
            items = self._get(
                f"/{resource_type}",
                params={"slug": slug, "per_page": 100, "context": "edit"},
            )
            for item in items:
                item_path = self._canonical_path(item.get("link", ""))
                if item_path == target_path:
                    return resource_type, int(item["id"]), item

            if items:
                # Fall back to slug match if the public link path differs from the crawled URL.
                return resource_type, int(items[0]["id"]), items[0]

        raise ValueError(f"Could not map URL/path '{page_id_or_path}' to a WordPress page or post.")

    def update_page_meta(self, page_id_or_path: str, title: Optional[str]=None, description: Optional[str]=None, canonical: Optional[str]=None):
        resource_type, resource_id, _ = self._resolve_resource(page_id_or_path)
        payload: Dict[str, Any] = {}
        if title: payload['title'] = title
        if description: payload['excerpt'] = description
        # Yoast-specific fields (must be exposed via REST in WP to persist)
        yoast_meta = {}
        if title: yoast_meta['_yoast_wpseo_title'] = title
        if description: yoast_meta['_yoast_wpseo_metadesc'] = description
        if yoast_meta:
            payload['meta'] = yoast_meta
        return self._put(f"/{resource_type}/{resource_id}", payload)

    def inject_json_ld(self, page_id_or_path: str, json_ld: Dict[str, Any]):
        resource_type, resource_id, item = self._resolve_resource(page_id_or_path)
        script = f"<script type=\"application/ld+json\">{json.dumps(json_ld)}</script>"
        current_content = (
            item.get("content", {}).get("raw")
            or item.get("content", {}).get("rendered")
            or ""
        )
        if script in current_content:
            return {"ok": True, "message": "JSON-LD already present."}
        updated_content = f"{current_content}\n{script}".strip()
        return self._put(f"/{resource_type}/{resource_id}", {"content": updated_content})

    def create_post(self, collection_or_path: str, title: str, html: str, slug: Optional[str]=None, date: Optional[str]=None, meta: Optional[Dict[str, Any]]=None):
        payload = {"title": title, "content": html, "status": "draft"}
        if slug: payload['slug'] = slug
        if date: payload['date'] = date
        if meta: payload['meta'] = meta
        return self._post("/posts", payload)

    def set_redirects(self, redirects: List[Tuple[str, str, int]]):
        # Requires a redirects plugin or custom endpoint; return a stub for now
        return {"ok": False, "message": "Redirects require a plugin or custom endpoint."}
