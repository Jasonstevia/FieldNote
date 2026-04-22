# blog_automation.py

from pathlib import Path
import os
from datetime import date, timedelta
# CORRECTED: Removed the non-existent 'llm_enabled'
from seo_common import genai_model, generate_with_fallback, today_iso
from context_store import load_context, save_context

class BlogAutomation:
    def __init__(self):
        self.name = "blog_automation"
        IS_VERCEL = os.environ.get('VERCEL') == '1'
        self.out_dir = Path('/tmp/drafts' if IS_VERCEL else 'drafts')
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _normalize_clusters(self, clusters_data):
        if isinstance(clusters_data, list):
            return clusters_data
        if isinstance(clusters_data, dict):
            if isinstance(clusters_data.get("topic_clusters"), list):
                return clusters_data["topic_clusters"]
            values = list(clusters_data.values())
            if len(values) == 1 and isinstance(values[0], list):
                return values[0]
            return [v for v in values if isinstance(v, dict)]
        return []

    def schedule_blogs(self, session_id: str, days: int = 7, generate_drafts: bool = True) -> dict:
        ctx = load_context(session_id)
        if not ctx: return {"error": "No snapshot found."}
        days = min(days, int(os.environ.get("DEMO_BLOG_DRAFTS", "5")))
        clusters_data = (ctx.get("agents", {}).get("topical_map", {}).get("clusters") or {})
        clusters_list = self._normalize_clusters(clusters_data)
        if not clusters_list:
            ctx.setdefault("agents", {}).setdefault("blog_automation", {})["schedule"] = []
            ctx["agents"]["blog_automation"]["created_at"] = today_iso()
            save_context(session_id, ctx)
            return {"status": "ok", "scheduled": 0, "schedule": []}
        queue = []
        for cluster in clusters_list:
            if isinstance(cluster, dict):
                cluster_name = cluster.get("pillar_page_title", "General")
                for sub in cluster.get("subtopics", []):
                    queue.append({
                        "cluster": cluster_name,
                        "title": sub.get("title"),
                        "keywords": sub.get("keywords", [])
                    })

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

            if generate_drafts:
                md = self._draft_markdown(ctx, item, model)
                try:
                    path.write_text(md, encoding="utf-8")
                    entry["status"] = "drafted"
                except Exception as e:
                    print(f"Error writing draft file to {path}: {e}")
                    entry["status"] = "drafted_inline"
                    entry["draft_content"] = md
            schedule.append(entry)

        ctx.setdefault("agents", {}).setdefault("blog_automation", {})["schedule"] = schedule
        ctx["agents"]["blog_automation"]["created_at"] = today_iso()
        save_context(session_id, ctx)
        return {"status": "ok", "scheduled": len(schedule), "schedule": schedule}

    def _draft_markdown(self, ctx: dict, item: dict, model):
        site = ctx.get("website", {}).get("url", "")
        prompt = f"""Write a 700-word, SEO-friendly blog post in Markdown. Title: {item['title']} Keywords: {", ".join(item.get("keywords", []))} Brand: {ctx.get("business", {}).get("name", "Brand")} Tone: {ctx.get("business", {}).get("constraints", {}).get("brand_tone", "helpful, expert")} Website: {site}. Return **Markdown only**."""
        try:
            resp = generate_with_fallback(prompt)
            if not resp:
                raise RuntimeError("LLM unavailable")
            return resp.text or f"# {item['title']}\n\n(Draft unavailable)"
        except Exception:
            keywords = ", ".join(item.get("keywords", [])[:5])
            return (
                f"# {item['title']}\n\n"
                f"## Why this topic matters\n\n"
                f"This draft covers {item['title'].lower()} in a clear, SEO-friendly format.\n\n"
                f"## Key points\n\n"
                f"- Primary keyword focus: {keywords or item['title'].lower()}\n"
                f"- Audience intent: informational\n"
                f"- Suggested CTA: learn more on the main website\n\n"
                f"## Draft placeholder\n\n"
                f"This is a fallback draft generated because the live AI writer was unavailable."
            )
