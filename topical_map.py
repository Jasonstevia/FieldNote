# topical_map.py

import json
# CORRECTED: Removed the non-existent 'llm_enabled'
from seo_common import genai_model, safe_json, today_iso
from context_store import load_context, save_context

class TopicalMap:
    def __init__(self):
        self.name = "topical_map"

    def generate_map(self, session_id: str) -> dict:
        ctx = load_context(session_id)
        if not ctx or "website" not in ctx:
            return {"error": "No snapshot found."}

        site = ctx["website"].get("url","")
        biz = ctx.get("business", {})
        model = genai_model()

        seeds = [s for p in ctx["website"].get("pages", []) for s in p.get("h1", []) + p.get("h2", []) if s]
        seeds = list(dict.fromkeys(seeds))[:30]

        if not model:
            return {"error": "LLM not configured. Cannot generate topical map."}

        prompt = f"""You are an SEO strategist. Build a compact topical map for the business below. Business name: {biz.get('name','')} Website: {site} Seed headings: {json.dumps(seeds, ensure_ascii=False)} Output JSON with ~5 topic clusters; each cluster has: "pillar_page_title" and "subtopics" (5-7 items with "title" and 3-5 "keywords"). No extra text."""
        
        try:
            resp = model.generate_content(prompt)
            clusters = safe_json(resp.text) or {}
        except Exception as e:
            clusters = {"error": f"LLM error: {e}"}

        ctx.setdefault("agents", {}).setdefault("topical_map", {})["clusters"] = clusters
        ctx["agents"]["topical_map"]["created_at"] = today_iso()
        save_context(session_id, ctx)

        return {"status": "ok", "clusters": clusters}