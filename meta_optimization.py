# meta_optimization.py

# CORRECTED: Removed the non-existent 'llm_enabled' from the import list.
from seo_common import genai_model, generate_with_fallback, safe_json, today_iso
from context_store import load_context, save_context

class MetaOptimization:
    def __init__(self):
        self.name = "meta_optimization"

    def _fallback_meta(self, current_title: str, current_desc: str, h1: str) -> tuple[str, str]:
        fallback_title = (h1 or current_title or "SEO Optimized Page")[:60]
        if current_desc:
            fallback_desc = current_desc[:160]
        elif h1:
            fallback_desc = f"Learn more about {h1.lower()} and explore the key information on this page."[:160]
        else:
            fallback_desc = "Explore the key information and resources available on this page."[:160]
        return fallback_title, fallback_desc

    def optimize_meta_tags(self, session_id: str) -> dict:
        ctx = load_context(session_id)
        if not ctx or "website" not in ctx or "pages" not in ctx["website"]:
            return {"error": "No snapshot found."}

        pages = ctx["website"]["pages"]
        max_pages = int(__import__("os").environ.get("DEMO_MAX_PROPOSAL_PAGES", "8"))
        pages = pages[:max_pages]
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
                resp = generate_with_fallback(prompt)
                if not resp:
                    raise RuntimeError("LLM unavailable")
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
                new_title, new_desc = self._fallback_meta(current_title, current_desc, h1)
                proposals.append({
                    "page_url": url,
                    "before": {"title": current_title, "description": current_desc},
                    "after": {"title": new_title, "description": new_desc},
                    "reason": "Fallback meta refinement."
                })

        ctx.setdefault("agents", {}).setdefault("meta_optimization", {})["proposals"] = proposals
        ctx["agents"]["meta_optimization"]["created_at"] = today_iso()
        save_context(session_id, ctx)

        return {"status": "ok", "count": len([p for p in proposals if 'error' not in p]), "proposals": proposals}
