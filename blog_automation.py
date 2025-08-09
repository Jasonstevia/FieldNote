# blog_automation.py

from pathlib import Path
import os
from datetime import date, timedelta
# CORRECTED: Removed the non-existent 'llm_enabled'
from seo_common import genai_model, today_iso
from context_store import load_context, save_context

class BlogAutomation:
    def __init__(self):
        self.name = "blog_automation"
        IS_VERCEL = os.environ.get('VERCEL') == '1'
        self.out_dir = Path('/tmp/drafts' if IS_VERCEL else 'drafts')
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def schedule_blogs(self, session_id: str, days: int = 7, generate_drafts: bool = True) -> dict:
        ctx = load_context(session_id)
        if not ctx: return {"error": "No snapshot found."}
        clusters = (ctx.get("agents", {}).get("topical_map", {}).get("clusters") or {})
        if not clusters: return {"error": "No topical clusters found."}

        queue = [
            {"cluster": name, "title": sub.get("title"), "keywords": sub.get("keywords", [])}
            for name, cluster in clusters.items() for sub in cluster.get("subtopics", [])
        ]
        seen = set()
        queue = [q for q in queue if q["title"] and not (q["title"] in seen or seen.add(q["title"]))]
        
        schedule = []
        model = genai_model()
        start_date = date.today()

        for i, item in enumerate(queue[:days]):
            post_date = start_date + timedelta(days=i)
            date_str = post_date.isoformat()
            
            safe_title = item['title'].replace(' ', '-').replace('?', '').replace('/', '').lower()[:60]
            fname = f"{date_str}-{safe_title}.md"
            path = self.out_dir / fname
            
            entry = { "date": date_str, "title": item["title"], "cluster": item["cluster"], "keywords": item["keywords"], "status": "scheduled", "draft_path": str(path) }

            if generate_drafts and model:
                md = self._draft_markdown(ctx, item, model)
                try:
                    path.write_text(md, encoding="utf-8")
                    entry["status"] = "drafted"
                except Exception as e:
                    print(f"Error writing draft file to {path}: {e}")
                    entry["status"] = "schedule_error"
            schedule.append(entry)

        ctx.setdefault("agents", {}).setdefault("blog_automation", {})["schedule"] = schedule
        ctx["agents"]["blog_automation"]["created_at"] = today_iso()
        save_context(session_id, ctx)
        return {"status": "ok", "scheduled": len(schedule), "schedule": schedule}

    def _draft_markdown(self, ctx: dict, item: dict, model):
        site = ctx.get("website", {}).get("url", "")
        prompt = f"""Write a 700-word, SEO-friendly blog post in Markdown. Title: {item['title']} Keywords: {", ".join(item.get("keywords", []))} Brand: {ctx.get("business", {}).get("name", "Brand")} Tone: {ctx.get("business", {}).get("constraints", {}).get("brand_tone", "helpful, expert")} Website: {site}. Return **Markdown only**."""
        try:
            resp = model.generate_content(prompt)
            return resp.text or f"# {item['title']}\n\n(Draft unavailable)"
        except Exception:
            return f"# {item['title']}\n\n(Draft generation error)"