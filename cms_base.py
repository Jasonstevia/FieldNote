
from typing import Any, Dict, List, Optional, Tuple

class CMSClient:
    """Abstract adapter interface for CMS / platform updates."""
    def update_page_meta(self, page_id_or_path: str, title: Optional[str]=None, description: Optional[str]=None, canonical: Optional[str]=None) -> Dict[str, Any]:
        raise NotImplementedError

    def inject_json_ld(self, page_id_or_path: str, json_ld: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def create_post(self, collection_or_path: str, title: str, html: str, slug: Optional[str]=None, date: Optional[str]=None, meta: Optional[Dict[str, Any]]=None) -> Dict[str, Any]:
        raise NotImplementedError

    def set_redirects(self, redirects: List[Tuple[str, str, int]]) -> Dict[str, Any]:
        """List of (from, to, status)."""
        raise NotImplementedError

def get_client(platform: str, creds: Dict[str, Any]):
    platform = (platform or '').lower()
    if platform in ('wordpress', 'wp'):
        from wordpress_adapter import WordPressAdapter
        return WordPressAdapter(creds)
    if platform == 'shopify':
        from shopify_adapter import ShopifyAdapter
        return ShopifyAdapter(creds)
    if platform == 'webflow':
        from webflow_adapter import WebflowAdapter
        return WebflowAdapter(creds)
    if platform == 'wix':
        from wix_adapter import WixAdapter
        return WixAdapter(creds)
    if platform == 'git':
        from git_pr_adapter import GitPRAdapter
        return GitPRAdapter(creds)
    if platform == 'patch':
        from patch_pack_adapter import PatchPackAdapter
        return PatchPackAdapter(creds)
    raise ValueError(f"Unsupported platform: {platform}")
