# blog_automation.py

from pathlib import Path
import os
from seo_common import genai_model, llm_enabled, today_iso
from context_store import load_context, save_context

class BlogAutomation:
    """Create a daily blog schedule and (optionally) draft content to /drafts."""

    def __init__(self):
        self.name = "blog_automation"
        # Determine the correct writable directory based on the environment
        IS_VERCEL = os.environ.get('VERCEL') == '1'
        self.out_dir = Path('/tmp/drafts' if IS_VERCEL else 'drafts')
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def schedule_blogs(self, session_id: str, days: int = 7, generate_drafts: bool = True) -> dict:
        ctx = load_context(session_id)
        if not ctx:
            return {"error": "No snapshot found."}

        clusters = (ctx.get("agents", {}).get("topical_map", {}).get("clusters") or {})
        if not clusters:
            return {"error": "No topical clusters found. Run TopicalMap.generate_map first."}

        queue = []
        for cluster_name, cluster in clusters.items():
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

        for i, item in enumerate(queue[:days]):
            date = today_iso()
            safe_title = item['title'].replace(' ', '-').replace('?', '').replace('/', '').lower()[:60]
            fname = f"{date}-{safe_title}.md"
            path = self.out_dir / fname
            
            entry = {
                "date": date,
                "title": item["title"],
                "cluster": item["cluster"],
                "keywords": item["keywords"],
                "status": "scheduled",
                "draft_path": str(path) # Store the path regardless
            }

            if generate_drafts:
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
        # ... (This function does not need any changes)
        site = ctx.get("website", {}).get("url", "")
        title = item["title"]
        kws = ", ".join(item.get("keywords", []))
        brand = ctx.get("business", {}).get("name", "Brand")
        tone = ctx.get("business", {}).get("constraints", {}).get("brand_tone", "helpful, expert")
        if not model:
            return f"# {title}\n\n*Keywords: {kws}*\n\nIntro about {brand} and {title}.\n\n## Key Points\n- Point A\n- Point B\n\n## CTA\nExplore more at {site}."
        prompt = f"""
Write a 700-word, SEO-friendly blog post in Markdown.

Title: {title}
Keywords: {kws}
Brand: {brand}
Tone: {tone}
Website: {site}

Sections: introduction, 2–3 subsections with H2, a bullet list, and a CTA that references the brand.
Return **Markdown only**.
"""
        try:
            resp = model.generate_content(prompt)
            return resp.text or f"# {title}\n\n(Draft unavailable)"
        except Exception:
            return f"# {title}\n\n(Draft generation error)"