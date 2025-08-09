# onpage_seo.py

import json
from bs4 import BeautifulSoup
from seo_common import genai_model, safe_json, today_iso
from context_store import load_context, save_context

class OnPageSEO:
    """
    Analyzes a page's full HTML and proposes a comprehensive technical SEO rewrite.
    This includes semantic HTML structure, schema generation, image alt text, and internal linking.
    """
    def __init__(self):
        self.name = "onpage_seo"

    def analyze_website(self, session_id: str) -> dict:
        ctx = load_context(session_id)
        if not ctx or "website" not in ctx or "pages" not in ctx["website"]:
            return {"error": "No snapshot found. Build the weekly snapshot first."}

        pages = ctx["website"]["pages"]
        model = genai_model()
        proposals = []

        for page in pages:
            url = page.get("url")
            original_html = page.get("html", "")
            if not original_html or not model:
                continue

            soup = BeautifulSoup(original_html, 'html.parser')
            # CORRECTED: Use .get('src') to prevent crashes on images without a src attribute.
            images_without_alt = [img.get('src', '') for img in soup.find_all('img') if img.get('src') and not img.get('alt', '').strip()]

            # CORRECTED: The prompt now specifies the correct "@type" for valid JSON-LD schema.
            prompt = f"""
            You are "FieldNote", a world-class technical SEO expert and web developer.
            Your task is to completely rewrite the body of a webpage for optimal technical and on-page SEO.

            **Analysis Context:**
            - Page URL: {url}
            - Business Name: {ctx.get('business', {}).get('name', '')}
            - Brand Tone: {ctx.get('business', {}).get('constraints', {}).get('brand_tone', 'expert, helpful')}
            - Images missing alt text: {json.dumps(images_without_alt)}

            **Instructions:**
            1. **Rewrite HTML Body:** Analyze the provided original HTML `<body>`. Rewrite it to be semantically correct and SEO-optimized. Ensure a single, compelling <h1>, logical structure, integrated keywords, and descriptive `alt` attributes for all `<img>` tags.
            2. **Generate Schema:** Based on the content, generate one primary JSON-LD schema block (e.g., Article, FAQPage, Product). It must be rich and detailed.

            **Output Format:**
            Return a single, minified JSON object with NO extra text or markdown.
            The JSON must have these exact keys:
            {{
                "reason_for_changes": "A brief, one-sentence explanation of the core improvements made.",
                "rewritten_html_body": "<body class=...><!-- a complete, single-line string of the new body HTML --></body>",
                "json_ld_schema": {{ "@context": "https://schema.org", "@type": "...", "..." }}
            }}

            **Original HTML to analyze:**
            ```html
            {original_html}
            ```
            """
            try:
                resp = model.generate_content(prompt)
                data = safe_json(resp.text) or {}
                if data.get("rewritten_html_body") and data.get("json_ld_schema"):
                    proposals.append({
                        "page_url": url,
                        "reason": data.get("reason_for_changes", "Comprehensive technical SEO rewrite."),
                        "proposed_html_body": data["rewritten_html_body"],
                        "proposed_schema": data["json_ld_schema"],
                    })
                else:
                    proposals.append({"page_url": url, "error": "LLM failed to generate valid HTML/Schema proposal.", "raw_response": resp.text})
            except Exception as e:
                proposals.append({"page_url": url, "error": f"LLM error during analysis: {e}"})

        ctx.setdefault("agents", {}).setdefault("onpage_seo", {})["proposals"] = proposals
        ctx["agents"]["onpage_seo"]["created_at"] = today_iso()
        save_context(session_id, ctx)
        return {"status": "ok", "count": len([p for p in proposals if 'error' not in p]), "proposals": proposals}