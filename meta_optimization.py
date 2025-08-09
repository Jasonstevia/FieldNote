# meta_optimization.py

# CORRECTED: Removed the non-existent 'llm_enabled' from the import list.
from seo_common import genai_model, safe_json, today_iso
from context_store import load_context, save_context

class MetaOptimization:
    def __init__(self):
        self.name = "meta_optimization"

    def optimize_meta_tags(self, session_id: str) -> dict:
        ctx = load_context(session_id)
        if not ctx or "website" not in ctx or "pages" not in ctx["website"]:
            return {"error": "No snapshot found."}

        pages = ctx["website"]["pages"]
        model = genai_model() # This function correctly handles the check.
        proposals = []

        for p in pages:
            url = p.get("url")
            current_title = (p.get("meta_title") or p.get("title") or "")[:120]
            current_desc  = (p.get("meta_description") or "")[:320]
            h1 = " | ".join(p.get("h1") or [])

            # If the model failed to load, we just skip the AI part.
            if not model:
                continue

            prompt = f"""
You are an expert technical SEO. Propose a concise, compelling meta title (<=60 chars) and description (<=160 chars). Return **JSON** with keys: "title", "description". No extra text. Business Name: {ctx.get('business',{}).get('name','')} Page URL: {url} Current Title: {current_title} Current Description: {current_desc} Primary H1s: {h1} Site Theme: {ctx.get('business',{}).get('constraints',{}).get('brand_tone','')}
"""
            try:
                resp = model.generate_content(prompt)
                data = safe_json(resp.text) or {}
                new_title = (data.get("title") or current_title)[:60]
                new_desc  = (data.get("description") or current_desc)[:160]
                proposals.append({
                    "page_url": url,
                    "before": {"title": current_title, "description": current_desc},
                    "after":  {"title": new_title,   "description": new_desc},
                    "reason": "LLM meta refinement."
                })
            except Exception as e:
                proposals.append({"page_url": url, "error": f"LLM error: {e}"})

        ctx.setdefault("agents", {}).setdefault("meta_optimization", {})["proposals"] = proposals
        ctx["agents"]["meta_optimization"]["created_at"] = today_iso()
        save_context(session_id, ctx)

        return {"status": "ok", "count": len([p for p in proposals if 'error' not in p]), "proposals": proposals}