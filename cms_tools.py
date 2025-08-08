#cms_tools.py

import json
import requests
import base64
from typing import List
from bs4 import BeautifulSoup, NavigableString

class CmsTool:
    """
    A base class for all CMS interaction tools.
    Defines the contract that all tools must follow.
    """
    def __init__(self, site_url: str, api_keys:dict):
        if not site_url or not api_keys or not api_keys.get("user") or not api_keys.get("password"):
            raise ValueError("Site URL, Username, and Application Password are required.")
        
        self.site_url = site_url.rstrip('/')
        # Prepare headers for WordPress REST API using Application Passwords (best practice)

        credentials = f"{api_keys['user']}:{api_keys['password']}"
        token = base64.b64encode(credentials.encode())
        self.headers = {'Authorization': f'Basic {token.decode("utf-8")}'}
        print(f"CmsTool initialized for {self.site_url}")

    def apply_onpage_changes(self, proposals: list) -> dict:
        raise NotImplementedError
    
    def apply_meta_changes(self, proposals: list) -> dict:
        raise NotImplementedError
    
    def publish_blog_posts(self, schedule: list) -> dict:
        raise NotImplementedError
    

class WordPressTool(CmsTool):
    """Functional tool for interacting with WordPress sites via REST API."""
    def __get_post_data_by_url(self, url:str) -> dict | None:
        """Finds a WordPress post/page ID and its raw content from its public URL"""
        slug = url.rstrip('/').split('/')[-1]
        if not slug: slug = "home"
        post_types = ["pages", "posts"]
        for post_type in post_types:
            api_url = f"{self.site_url}/wp-json/wp/v2/{post_type}?slug={slug}&context=edit"
            try:
                res = requests.get(api_url, headers=self.headers, timeout=15)
                res.raise_for_status()
                data = res.json()
                if data:
                    return data[0]
            except requests.exceptions.RequestException as e:
                print(f"Error finding {post_type} with slug {slug}: {e}")
        return None

    def apply_meta_changes(self, proposals: List[dict]) -> dict:
        """Applies meta title & description changes, assuming a common SEO plugin like Yoast"""
        print(f"--- WordPressTool: Applying {len(proposals)} meta tag changes... ---")
        updated_count = 0
        errors = []
        for proposal in proposals:
            if 'error' in proposal: continue
            post_data = self.__get_post_data_by_url(proposal['page_url'])
            if not post_data:
                errors.append(f"Could not find WP ID for URL: {proposal['page_url']}")
                continue

            # This payload assumes Yoast SEO plugin is installed, which is very common.
            # The meta fields are '_yoast_wpseo_title' and '_yoast_wpseo_metadesc'.
            payload = {
                "meta": {
                    "__yoast_wpseo_title": proposal['after']['title'],
                    "__yoast_wpseo_metadesc": proposal['after']['description']
                }
            }
            api_url = f"{self.site_url}/wp-json/wp/v2/{post_data['type']}s/{post_data['id']}"
            try:
                res = requests.post(api_url, headers=self.headers, json=payload)
                res.raise_for_status()
                updated_count += 1
            except requests.exceptions.RequestException as e:
                errors.append(f"Failed to update meta for {proposal['page_url']}: {e}")
        return {"status": "ok", "message": f"Applied {updated_count}/{len(proposals)} meta tag updates to Wordpress", "errors": errors}

    def publish_blog_posts(self, schedule: List[dict]) -> dict:
        """Reads blog drafts and publishes them as new posts in WordPress."""
        print(f"--- WordPressTool: Publishing {len(schedule)} blog posts... ---")
        published_count = 0
        errors = []
        for post_data in schedule:
            try:
                with open(post_data['draft_path'], 'r', encoding='utf-8') as f:
                    content = f.read()
            except FileNotFoundError:
                errors.append(f"Draft file not found: {post_data['draft_path']}")
                continue

            payload = {
                "title": post_data['title'],
                "content": content,
                "status": "publish",
            }
            api_url = f"{self.site_url}/wp-json/wp/v2/posts"
            try:
                res = requests.post(api_url, headers=self.headers, json=payload)
                res.raise_for_status()
                published_count += 1
            except requests.exceptions.RequestException as e:
                errors.append(f"Failed to publish post '{post_data['title']}': {e}")

        return {
            "status": "ok",
            "message": f"Published {published_count}/{len(schedule)} blog posts to WordPress",
            "errors": errors
        }
    
    def apply_onpage_changes(self, proposals: list[dict]) -> dict:
        """
        Applies the complete, rewritten HTML body and schema to a Wordpress page.
        This is a full content replacement for maximum SEO impact.
        """
        print(f"--- WordPressTool: Applying {len(proposals)} full-page HTML rewrites... ---")
        updated_count = 0
        errors = []
        for proposal in proposals:
            if 'error' in proposal or not proposal.get("proposed_html_body"): 
                continue
            
            page_url = proposal['page_url']
            # 1. GET: Fetch the live post data from WordPress
            post_data = self.__get_post_data_by_url(page_url)
            if not post_data:
                errors.append(f"Could not find WP content for URL: {page_url}")
                continue

            post_id = post_data['id']
            post_type_plural = post_data['type'] + 's'

            # The payload now directly uses the rewritten HTML from the agent
            payload = {
                "content": proposal['proposed_html_body'],
                # We also add the schema to a custom meta field for SEO plugins to use
                "meta": {
                    "seo_pilot_json_ld_schema": json.dumps(proposal.get("proposed_schema", {}))
                }
            }
            api_url = f"{self.site_url}/wp-json/wp/v2/{post_type_plural}/{post_id}"
            try:
                res = requests.post(api_url, headers=self.headers, json=payload, timeout=20)
                res.raise_for_status()
                updated_count += 1
            except requests.exceptions.RequestException as e:
                errors.append(f"Failed to update on-page content for {page_url}: {e.response.text if e.response else e}")
        return {
            "status": "ok",
            "message": f"Successfully applied full HTML rewrites to {updated_count}/{len(proposals)} pages.",
            "errors": errors
        }
    
TOOL_REGISTRY = {

    "wordpress": WordPressTool, 
}

def get_cms_tool(platform_name: str, site_url: str, api_keys: dict) -> CmsTool:
    tool_class = TOOL_REGISTRY.get(platform_name.lower())
    if not tool_class:
        raise ValueError(f"No tool available for platform: {platform_name}")
    return tool_class(site_url, api_keys)