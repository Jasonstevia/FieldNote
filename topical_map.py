"""topical_map.py"""

import json
from seo_common import genai_model, llm_enabled, safe_json, today_iso
from context_store import load_context, save_context

class TopicalMap:
    """Generate a topical map from the snapshot's business/site info.
Writes clusters into context and returns the plan. No scraping.
"""
    def __init__(self):
        self.name = "topical_map"

    def generate_map(self, session_id: str) -> dict:
        ctx = load_context(session_id)
        if not ctx or "website" not in ctx:
            return {"error": "No snapshot found. Build the weekly snapshot first."}

        site = ctx["website"].get("url","")
        biz = ctx.get("business", {})
        model = genai_model()

        seeds = []
        for p in ctx["website"].get("pages", []):
            seeds.extend(p.get("h1", []))
            seeds.extend(p.get("h2", []))
        seeds = list(dict.fromkeys([s for s in seeds if s]))[:30]

        if not model:
            clusters = {}
            for s in seeds:
                key = s.split(" ")[0].lower()
                clusters.setdefault(key.capitalize(), { "pillar_page_title": f"{key.capitalize()} Guide", "subtopics": [] })
                clusters[key.capitalize()]["subtopics"].append({"title": s, "keywords": [s.lower()]})
        else:
            prompt = f"""
You are an SEO strategist. Build a compact topical map for the business below.

Business name: {biz.get('name','')}
Website: {site}
Brand tone: {biz.get('constraints',{}).get('brand_tone','')}

Seed headings from the site:
{json.dumps(seeds, ensure_ascii=False)}

Output JSON with ~5 topic clusters; each cluster has:
- "pillar_page_title"
- "subtopics": 5–7 items with "title" and 3–5 "keywords"
No extra text.
"""
            try:
                resp = model.generate_content(prompt)
                clusters = safe_json(resp.text) or {}
            except Exception as e:
                clusters = {"error": f"LLM error: {e}"}

        ctx.setdefault("agents", {}).setdefault("topical_map", {})["clusters"] = clusters
        ctx["agents"]["topical_map"]["created_at"] = today_iso()
        save_context(session_id, ctx)

        return {"status": "ok", "clusters": clusters}
