"""meta_optimization.py"""

from seo_common import genai_model, llm_enabled, safe_json, today_iso
from context_store import load_context, save_context

class MetaOptimization:
    """Propose meta title & description updates based on the weekly snapshot.
    Reads: .vibe_context/{session_id}.json
    Writes proposals under ctx["agents"]["meta_optimization"]["proposals"]
    """
    def __init__(self):
        self.name = "meta_optimization"

    def optimize_meta_tags(self, session_id: str) -> dict:
        ctx = load_context(session_id)
        if not ctx or "website" not in ctx or "pages" not in ctx["website"]:
            return {"error": "No snapshot found. Build the weekly snapshot first."}

        pages = ctx["website"]["pages"]
        model = genai_model()

        proposals = []
        for p in pages:
            url = p.get("url")
            current_title = (p.get("meta_title") or p.get("title") or "")[:120]
            current_desc  = (p.get("meta_description") or "")[:320]
            h1 = " | ".join(p.get("h1") or [])

            if not model:
                biz = ctx.get("business", {}) or {}
                new_title = (current_title[:57] + " – " + biz.get("name","")).strip()[:60] if current_title else f"{biz.get('name','Brand')} – {p.get('slug','Page')}"[:60]
                new_desc  = (current_desc or f"{biz.get('name','Brand')} {h1}".strip())[:155]
                proposals.append({
                    "page_url": url,
                    "before": {"title": current_title, "description": current_desc},
                    "after":  {"title": new_title,   "description": new_desc},
                    "reason": "Heuristic meta optimization without LLM (length/tone tweaks)."
                })
                continue

            prompt = f"""
You are an expert technical SEO.
Given this page context, propose a concise, compelling meta title (<=60 chars) and description (<=160 chars).
Return **JSON** with keys: "title", "description". No extra text.

Business Name: {ctx.get('business',{}).get('name','')}
Page URL: {url}
Current Title: {current_title}
Current Description: {current_desc}
Primary H1s: {h1}
Site Theme: {ctx.get('business',{}).get('constraints',{}).get('brand_tone','')}
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
                    "reason": "LLM meta refinement respecting length and brand tone."
                })
            except Exception as e:
                proposals.append({"page_url": url, "error": f"LLM error: {e}"})

        ctx.setdefault("agents", {}).setdefault("meta_optimization", {})["proposals"] = proposals
        ctx["agents"]["meta_optimization"]["created_at"] = today_iso()
        save_context(session_id, ctx)

        return {"status": "ok", "count": len([p for p in proposals if 'error' not in p]), "proposals": proposals}
