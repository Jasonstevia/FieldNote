# orchestrator.py

import asyncio
import json
import html
import os
import typing as t
from search_crawl import build_weekly_snapshot
from context_store import save_context, load_context
from topical_map import TopicalMap
from meta_optimization import MetaOptimization
from onpage_seo import OnPageSEO
from blog_automation import BlogAutomation
from cms_base import get_client
from seo_common import genai_model, generate_with_fallback

def _demo_mode_enabled() -> bool:
    return os.environ.get("DEMO_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}

def _safe_async_timeout() -> float:
    try:
        return float(os.environ.get("DEMO_AGENT_TIMEOUT_SECONDS", "12"))
    except Exception:
        return 12.0

def _slugify(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in (value or "post"))
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "post"

def _markdown_to_html(markdown_text: str) -> str:
    lines = (markdown_text or "").splitlines()
    html_parts: list[str] = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            html_parts.append("</ul>")
            in_list = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            close_list()
            continue
        if line.startswith("# "):
            close_list()
            html_parts.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            close_list()
            html_parts.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            close_list()
            html_parts.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{html.escape(line[2:].strip())}</li>")
        else:
            close_list()
            html_parts.append(f"<p>{html.escape(line)}</p>")

    close_list()
    return "\n".join(html_parts)

def _cluster_list(ctx: dict) -> list[dict]:
    clusters = ctx.get("agents", {}).get("topical_map", {}).get("clusters", [])
    if isinstance(clusters, dict):
        if isinstance(clusters.get("topic_clusters"), list):
            return clusters["topic_clusters"]
        values = list(clusters.values())
        if len(values) == 1 and isinstance(values[0], list):
            return values[0]
        return [v for v in values if isinstance(v, dict)]
    if isinstance(clusters, list):
        return clusters
    return []

def _seo_score(ctx: dict) -> tuple[int, list[str]]:
    pages = ctx.get("website", {}).get("pages", [])
    page_count = len(pages)
    if page_count == 0:
        return 0, ["No pages were successfully crawled yet."]

    pages_with_meta = sum(1 for p in pages if p.get("meta_description"))
    pages_with_h1 = sum(1 for p in pages if p.get("h1"))
    pages_with_canonical = sum(1 for p in pages if p.get("canonical"))
    avg_internal_links = sum(len(p.get("internal_links", [])) for p in pages) / max(page_count, 1)

    score = 40
    score += round((pages_with_meta / page_count) * 20)
    score += round((pages_with_h1 / page_count) * 20)
    score += round((pages_with_canonical / page_count) * 10)
    score += 10 if avg_internal_links >= 5 else 5 if avg_internal_links >= 2 else 0
    score = max(0, min(score, 100))

    recommendations = []
    if pages_with_meta < page_count:
        recommendations.append("Add or improve meta descriptions on pages where they are missing.")
    if pages_with_h1 < page_count:
        recommendations.append("Fix heading structure so each page has a clear primary H1.")
    if pages_with_canonical < page_count:
        recommendations.append("Add canonical tags consistently to strengthen indexation signals.")
    if avg_internal_links < 5:
        recommendations.append("Improve internal linking between related pages to support crawl depth and topic authority.")
    if not recommendations:
        recommendations.append("Use the generated review plan to refine titles, schema, and supporting content for higher CTR and topical coverage.")

    return score, recommendations

def _approval_intent(text: str) -> bool:
    lowered = (text or "").lower()
    phrases = [
        "yes",
        "yes please",
        "go ahead",
        "continue",
        "proceed",
        "do it",
        "generate it",
        "show me the plan",
        "create the plan",
        "let's do it",
        "lets do it",
    ]
    return any(phrase in lowered for phrase in phrases)

def _grounded_chat_context(ctx: dict) -> str:
    pages = ctx.get("website", {}).get("pages", [])
    platform = ctx.get("website", {}).get("platform", "unknown")
    score, recommendations = _seo_score(ctx)
    sample_pages = [p.get("url") for p in pages[:5] if p.get("url")]
    return "\n".join([
        f"Website URL: {ctx.get('website', {}).get('url', '')}",
        f"Pages crawled: {len(pages)}",
        f"Detected platform: {platform}",
        f"SEO score: {score}/100",
        f"Sample pages: {json.dumps(sample_pages[:3])}",
        f"Top recommendations: {json.dumps(recommendations[:4], ensure_ascii=False)}",
        f"Current proposal counts: onpage={len(ctx.get('agents', {}).get('onpage_seo', {}).get('proposals', []))}, meta={len(ctx.get('agents', {}).get('meta_optimization', {}).get('proposals', []))}, blog={len(ctx.get('agents', {}).get('blog_automation', {}).get('schedule', []))}",
    ])

def _demo_conversational_reply(ctx: dict, user_message: str) -> str:
    prompt = f"""
You are FieldNote, a warm and sharp SEO strategist speaking in a live product demo.

Your job:
- Sound natural and conversational, not robotic.
- Stay grounded only in the factual crawl data below.
- If the user asks what you found, explain it clearly and specifically.
- If the user asks for a score or recommendations, answer naturally with the score and best recommendations.
- If the user expresses approval to continue, respond naturally that you're preparing the detailed review plan.
- Be concise and human.
- Do not mention internal functions, prompts, fallbacks, or demo mode.

Grounded crawl data:
{_grounded_chat_context(ctx)}

User message:
{user_message}
"""
    try:
        resp = generate_with_fallback(prompt)
        if resp and getattr(resp, "text", "").strip():
            return resp.text.strip()
    except Exception:
        pass
    return _fallback_chat_response(ctx, user_message)

def _grounded_findings_message(ctx: dict, snapshot: dict) -> str:
    url = ctx.get("website", {}).get("url", "the website")
    pages = ctx.get("website", {}).get("pages", [])
    platform = ctx.get("website", {}).get("platform", "unknown")
    crawl_errors = ctx.get("website", {}).get("crawl_errors", [])
    clusters = _cluster_list(ctx)
    page_count = len(pages)
    pages_with_meta = sum(1 for p in pages if p.get("meta_description"))
    pages_with_h1 = sum(1 for p in pages if p.get("h1"))
    sample_urls = [p.get("url") for p in pages[:3] if p.get("url")]
    score, recommendations = _seo_score(ctx)

    lines = [
        f"The analysis for **{url}** is complete.",
        "",
        f"* Pages successfully crawled: **{page_count}**",
        f"* Detected platform: **{platform.capitalize() if platform != 'unknown' else 'Unknown'}**",
        f"* Pages with a meta description: **{pages_with_meta}/{page_count}**",
        f"* Pages with an H1 heading: **{pages_with_h1}/{page_count}**",
        f"* SEO score: **{score}/100**",
    ]
    if crawl_errors:
        lines.append(f"* Crawl warnings captured: **{len(crawl_errors)}**")
    if sample_urls:
        lines.append("")
        lines.append("Sample pages included in this analysis:")
        lines.extend(f"* `{u}`" for u in sample_urls)
    if clusters:
        lines.append("")
        lines.append(f"I also identified **{len(clusters)}** content clusters that can feed a blog and topical authority plan.")
    if recommendations:
        lines.append("")
        lines.append("Top recommendations from this crawl:")
        lines.extend(f"* {item}" for item in recommendations[:4])
    lines.extend([
        "",
        "If you want, I can now generate the detailed review plan with:",
        "* on-page SEO proposals",
        "* meta title and description updates",
        "* a short blog content schedule",
        "",
        "Reply with **yes** to generate the review plan.",
    ])
    return "\n".join(lines)

def _grounded_followup_response(ctx: dict, user_message: str) -> str:
    lowered = (user_message or "").lower()
    page_count = len(ctx.get("website", {}).get("pages", []))
    platform = ctx.get("website", {}).get("platform", "unknown")
    sample_pages = [p.get("url") for p in ctx.get("website", {}).get("pages", [])[:5] if p.get("url")]
    score, recommendations = _seo_score(ctx)

    if any(term in lowered for term in ["score", "recommendation", "recommendations", "seo score"]):
        lines = [
            f"My grounded SEO score from the crawl is **{score}/100**.",
            "",
            f"* Pages crawled: **{page_count}**",
            f"* Detected platform: **{platform.capitalize() if platform != 'unknown' else 'Unknown'}**",
            "",
            "Top recommendations:",
        ]
        lines.extend(f"* {item}" for item in recommendations[:4])
        if sample_pages:
            lines.extend([
                "",
                "Sample crawled pages behind this score:",
            ])
            lines.extend(f"* `{u}`" for u in sample_pages[:3])
        lines.extend([
            "",
            "If you want, reply with **yes** or **go ahead** and I’ll generate the detailed review plan.",
        ])
        return "\n".join(lines)

    if any(term in lowered for term in ["what did you find", "what did you actually find", "specific"]):
        lines = [
            "Here is the grounded summary from the crawl data I actually collected:",
            "",
            f"* Pages crawled: **{page_count}**",
            f"* Detected platform: **{platform.capitalize() if platform != 'unknown' else 'Unknown'}**",
        ]
        if sample_pages:
            lines.append("* Sample crawled URLs:")
            lines.extend(f"* `{u}`" for u in sample_pages[:3])
        return "\n".join(lines)

    return (
        f"I crawled **{page_count}** pages and the current grounded score is **{score}/100**. "
        "If you want the exact proposed changes, reply with **yes** or **go ahead** and I’ll generate the review plan."
    )

def _grounded_plan_ready_message(ctx: dict) -> str:
    onpage_count = len(ctx.get("agents", {}).get("onpage_seo", {}).get("proposals", []))
    meta_count = len(ctx.get("agents", {}).get("meta_optimization", {}).get("proposals", []))
    blog_count = len(ctx.get("agents", {}).get("blog_automation", {}).get("schedule", []))
    lines = [
        "The review plan is ready.",
        "",
        f"* On-page SEO proposals: **{onpage_count}**",
        f"* Meta optimization proposals: **{meta_count}**",
        f"* Blog draft slots: **{blog_count}**",
        "",
        "Open the review panel to inspect the exact proposed changes.",
    ]
    if _demo_mode_enabled():
        lines.extend([
            "",
            "This session is running in **demo mode**, so the focus is on reviewing and discussing the proposed SEO changes, not executing them on the live site.",
        ])
    else:
        platform = ctx.get("website", {}).get("platform", "unknown").capitalize()
        if platform.lower() == "wordpress":
            lines.extend([
                "",
                "If the plan looks good, the next step is to provide WordPress credentials to execute it.",
            ])
        else:
            lines.extend([
                "",
                f"Execution is currently automated only for **WordPress**. For **{platform}**, this review plan is intended as a manual implementation guide.",
            ])
    return "\n".join(lines)

async def _run_generation_step(label: str, fn, session_id: str) -> dict | None:
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, session_id), timeout=_safe_async_timeout())
    except Exception as e:
        return {"error": f"{label} failed: {e}"}

def _fallback_chat_response(ctx: dict, user_message: str) -> str:
    lowered = (user_message or "").lower()
    page_count = len(ctx.get("website", {}).get("pages", []))
    platform = ctx.get("website", {}).get("platform", "unknown")
    onpage_count = len(ctx.get("agents", {}).get("onpage_seo", {}).get("proposals", []))
    meta_count = len(ctx.get("agents", {}).get("meta_optimization", {}).get("proposals", []))
    blog_count = len(ctx.get("agents", {}).get("blog_automation", {}).get("schedule", []))
    score, recommendations = _seo_score(ctx)

    if any(term in lowered for term in ["what did you find", "what did you actually find", "specific", "found on the site"]):
        sample_pages = [p.get("url") for p in ctx.get("website", {}).get("pages", [])[:5] if p.get("url")]
        lines = [
            f"Here’s the grounded SEO readout from the crawl for **{ctx.get('website', {}).get('url', 'this site')}**:",
            "",
            f"* Pages crawled: **{page_count}**",
            f"* Detected platform: **{platform.capitalize() if platform != 'unknown' else 'Unknown'}**",
            f"* SEO score: **{score}/100**",
            "",
            "Main recommendations:",
        ]
        lines.extend(f"* {item}" for item in recommendations[:4])
        if sample_pages:
            lines.append("")
            lines.append("* Sample crawled URLs:")
            lines.extend(f"* `{u}`" for u in sample_pages[:3])
        return "\n".join(lines)

    if any(term in lowered for term in ["score", "recommendation", "recommendations", "seo score"]):
        score, recommendations = _seo_score(ctx)
        lines = [
            f"Based on the crawl, I’d score the site at **{score}/100** right now.",
            "",
            "My top recommendations would be:",
        ]
        lines.extend(f"* {item}" for item in recommendations[:4])
        lines.append("")
        lines.append("If you want, I can turn that into the full review plan next.")
        return "\n".join(lines)

    if _approval_intent(lowered):
        return "Perfect. I’ll turn that into the detailed review plan now so you can inspect the exact proposed changes."

    if onpage_count or meta_count or blog_count:
        return (
            "I already have the review plan populated from the crawl. "
            f"Right now that includes **{onpage_count}** on-page proposals, **{meta_count}** meta updates, "
            f"and **{blog_count}** blog draft slots."
        )

    return (
        f"I’ve already crawled **{page_count}** pages and the current grounded SEO score is **{score}/100**. "
        "If you want, I can break down the recommendations or go straight into the review plan."
    )

class Agent:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.model = genai_model()
        self.ctx = load_context(session_id) or {"history": [], "state": "start"}

    def chat(self, instruction: str) -> str:
        system_prompt = f"""
        You are "FieldNote", an expert AI SEO strategist.
        Your Persona: A helpful, data-driven, and clear expert. You explain the 'why' behind your suggestions in simple terms to build excitement and trust. NO EMOJIS.

        **CRITICAL RULES:**
        1.  Think step-by-step inside a `<thinking>` block (your internal monologue).
        2.  Your final response to the user must be outside the `<thinking>` block.
        3.  Use markdown (`*`, `**`) for clarity. Be SPECIFIC and use the data provided in the context.
        4.  NEVER mention your internal state or function names.

        ---
        **CONTEXT FOR THIS TURN:**
        *   Website URL: {self.ctx.get("url")}
        *   Detected Platform: {self.ctx.get("website", {}).get("platform", "Unknown")}
        *   Number of Pages Scanned: {len(self.ctx.get("website", {}).get("pages", []))}
        *   Proposed Blog Topics (if available): {json.dumps(self.ctx.get("agents", {}).get("topical_map", {}).get("clusters", {}))}
        ---

        **INSTRUCTION FOR THIS TURN:** "{instruction}"
        """
        if not self.model:
            return _fallback_chat_response(self.ctx, instruction)
        try:
            resp = generate_with_fallback(system_prompt)
            if not resp:
                return _fallback_chat_response(self.ctx, instruction)
            clean_response = resp.text.split('</thinking>')[-1].strip()
            return clean_response or "I have finished the step."
        except Exception as e:
            print(f"LLM Generation Error: {e}")
            return _fallback_chat_response(self.ctx, instruction)

async def run_orchestrator_turn(session_id: str, user_message: str, api_keys: t.Optional[dict] = None) -> t.List[dict]:
    agent = Agent(session_id)
    state = agent.ctx.get("state", "start")
    messages = []

    if state == "start" and user_message.startswith("analyze:"):
        url = user_message.split("analyze:", 1)[1].strip()
        agent.ctx["url"] = url
        agent.ctx["state"] = "discovery"
        save_context(session_id, agent.ctx)
        
        messages.append({"agent": "orchestrator", "text": f"Initializing analysis for **{url}**...", "status": "in_progress"})
        
        try:
            messages.append({"agent": "orchestrator", "text": "Scraping website structure and content...", "status": "in_progress"})
            snapshot = await build_weekly_snapshot(session_id, url, max_pages=50)
            agent.ctx = load_context(session_id)

            if snapshot.get("pages", 0) <= 0:
                crawl_errors = agent.ctx.get("website", {}).get("crawl_errors", [])
                agent.ctx["state"] = "crawl_failed"
                save_context(session_id, agent.ctx)
                error_hint = f" Recent crawl errors: {crawl_errors[:2]}" if crawl_errors else ""
                messages.append({
                    "agent": "orchestrator",
                    "text": (
                        f"I couldn't extract any HTML pages from **{url}**, so I don't have real page-level SEO data to analyze yet."
                        f"{error_hint}\n\n"
                        f"That means I should **not** generate a technical action plan yet, because the review would be empty."
                        f"\n\n"
                        f"Please try one of these next:\n"
                        f"* Retry the analysis in a minute.\n"
                        f"* Test with another public URL from the same site, like a deeper content page.\n"
                        f"* If you need a guaranteed demo for tomorrow, I can help you switch this project into a safe **demo mode** that shows the full workflow with mock AI outputs."
                    ),
                })
            else:
                messages.append({"agent": "orchestrator", "text": "Identifying content gaps and blog opportunities...", "status": "in_progress"})
                TopicalMap().generate_map(session_id)
                agent.ctx = load_context(session_id)

                messages.append({"agent": "orchestrator", "text": "Finalizing SEO score and recommendations...", "status": "in_progress"})
                await asyncio.sleep(1.5)

                agent.ctx["state"] = "presenting_findings"
                save_context(session_id, agent.ctx)

                if _demo_mode_enabled():
                    agent_response = _grounded_findings_message(agent.ctx, snapshot)
                else:
                    instruction = f"The analysis of {url} is complete. It has {snapshot.get('pages', 0)} pages and the platform is {snapshot.get('platform', 'unknown')}. Present the findings to the user. Be specific and exciting using the context data. Give a score. End by asking for permission to generate the full action plan."
                    agent_response = agent.chat(instruction)
                    if not agent_response or "LLM is not configured." in agent_response or agent_response.startswith("Error connecting to AI model"):
                        agent_response = _grounded_findings_message(agent.ctx, snapshot)
                messages.append({"agent": "orchestrator", "text": agent_response})

        except Exception as e:
            messages.append({"agent": "orchestrator", "text": f"An error occurred during discovery: {e}"})
            agent.ctx["state"] = "error"; save_context(session_id, agent.ctx)

    elif state == "presenting_findings":
        if _demo_mode_enabled():
            if _approval_intent(user_message):
                agent_response = "Perfect. I’m putting together the detailed review plan now based on the pages I crawled."
            else:
                agent_response = _demo_conversational_reply(agent.ctx, user_message)
        else:
            instruction = f"The user has responded to your analysis with: '{user_message}'. If they've given approval (e.g., 'yes', 'ok', 'sure'), confirm you're generating the detailed action plan. If they ask a question, answer it. Otherwise, gently nudge them for approval."
            agent_response = agent.chat(instruction)
            if not agent_response or "LLM is not configured." in agent_response or agent_response.startswith("Error connecting to AI model"):
                agent_response = _fallback_chat_response(agent.ctx, user_message)
        messages.append({"agent": "orchestrator", "text": agent_response})
        
        if _approval_intent(user_message):
            agent.ctx["state"] = "generating_proposals"; save_context(session_id, agent.ctx)
            
            messages.append({"agent": "orchestrator", "text": "Preparing technical page rewrites...", "status": "in_progress"})
            onpage_result = await _run_generation_step("onpage_seo", OnPageSEO().analyze_website, session_id)
            
            messages.append({"agent": "orchestrator", "text": "Optimizing all meta titles and descriptions...", "status": "in_progress"})
            meta_result = await _run_generation_step("meta_optimization", MetaOptimization().optimize_meta_tags, session_id)

            messages.append({"agent": "orchestrator", "text": "Drafting all scheduled blog posts...", "status": "in_progress"})
            blog_result = await _run_generation_step("blog_automation", BlogAutomation().schedule_blogs, session_id)
            
            agent.ctx = load_context(session_id)
            agent.ctx.setdefault("agents", {}).setdefault("run_status", {})["onpage_seo"] = onpage_result or {"status": "unknown"}
            agent.ctx["agents"]["run_status"]["meta_optimization"] = meta_result or {"status": "unknown"}
            agent.ctx["agents"]["run_status"]["blog_automation"] = blog_result or {"status": "unknown"}
            agent.ctx["state"] = "awaiting_final_approval"; save_context(session_id, agent.ctx)
            platform = agent.ctx.get("website", {}).get("platform", "CMS").capitalize()
            if _demo_mode_enabled():
                agent_response_2 = _grounded_plan_ready_message(agent.ctx)
                actions = [{"type": "review_changes", "label": "Review Action Plan"}]
            else:
                instruction = "All proposals are now generated. Announce that the action plan is ready for review. Remind the user of the platform you detected and ask for the appropriate credentials to execute the plan."
                agent_response_2 = agent.chat(instruction)
                if not agent_response_2 or "LLM is not configured." in agent_response_2 or agent_response_2.startswith("Error connecting to AI model"):
                    agent_response_2 = _grounded_plan_ready_message(agent.ctx)
                actions = [{"type": "review_changes", "label": "Review Action Plan"}]
                if platform.lower() == "wordpress" and not _demo_mode_enabled():
                    actions.append({"type": "provide_keys", "label": f"Provide {platform} Credentials & Approve"})
                else:
                    agent_response_2 = (
                        f"{agent_response_2}\n\n"
                        f"Execution is currently automated only for **WordPress**. "
                        f"For **{platform}**, you can still review the generated plan and use it as a manual implementation guide."
                    )
            messages.append({"agent": "orchestrator", "text": agent_response_2, "actions": actions})
    elif state == "crawl_failed":
        messages.append({
            "agent": "orchestrator",
            "text": (
                "The last crawl did not produce any real pages, so I can't generate trustworthy SEO proposals yet. "
                "If you want, retry with another public URL from that site, or I can help you set up a demo mode for tomorrow."
            ),
        })
    else:
        messages.append({"agent": "orchestrator", "text": agent.chat(f"The user said: '{user_message}'. Respond helpfully.")})
    
    return messages

async def execute_with_keys(session_id: str, creds: dict) -> list[dict]:
    ctx = load_context(session_id)
    if not ctx:
        return [{"agent": "executor", "text": "Execution failed: no saved session context was found."}]

    platform = ctx.get("website", {}).get("platform", "unknown")
    site_url = ctx.get("website", {}).get("url")
    creds_with_url = {**creds, "site_url": site_url}
    logs = []
    try:
        client = get_client(platform, creds_with_url)
    except Exception as e:
        return [{"agent": "executor", "text": f"Execution setup failed: {e}"}]

    meta_proposals = ctx.get("agents", {}).get("meta_optimization", {}).get("proposals", [])
    for item in meta_proposals:
        try:
            res = client.update_page_meta(item['page_url'], item['after']['title'], item['after']['description'])
            if isinstance(res, dict) and res.get("ok") is False:
                logs.append({"agent": "executor", "text": f"Meta update for {item['page_url']}: Skipped ({res.get('message', 'not supported')})"})
            else:
                logs.append({"agent": "executor", "text": f"Meta update for {item['page_url']}: Success"})
        except Exception as e:
            logs.append({"agent": "executor", "text": f"Meta update FAILED for {item['page_url']}: {e}"})

    onpage_proposals = ctx.get("agents", {}).get("onpage_seo", {}).get("proposals", [])
    for p in onpage_proposals:
        try:
            if "proposed_schema" not in p:
                logs.append({"agent": "executor", "text": f"Schema inject skipped for {p.get('page_url')}: no generated schema was available"})
                continue
            res = client.inject_json_ld(p.get('page_url'), p.get('proposed_schema', {}))
            if isinstance(res, dict) and res.get("ok") is False:
                logs.append({"agent": "executor", "text": f"Schema inject for {p.get('page_url')}: Skipped ({res.get('message', 'not supported')})"})
            else:
                logs.append({"agent": "executor", "text": f"Schema inject for {p.get('page_url')}: Success"})
        except Exception as e:
            logs.append({"agent": "executor", "text": f"Schema inject FAILED for {p.get('page_url')}: {e}"})

    blog_schedule = ctx.get("agents", {}).get("blog_automation", {}).get("schedule", [])
    for b in blog_schedule:
        try:
            if b.get("draft_content"):
                draft_content = b["draft_content"]
            else:
                with open(b['draft_path'], 'r', encoding='utf-8') as f:
                    draft_content = f.read()
            html_content = _markdown_to_html(draft_content)
            res = client.create_post('blog', b.get('title'), html_content, slug=_slugify(b.get('title', 'post')))
            if isinstance(res, dict) and res.get("ok") is False:
                logs.append({"agent": "executor", "text": f"Blog post '{b.get('title')}': Skipped ({res.get('message', 'not supported')})"})
            else:
                logs.append({"agent": "executor", "text": f"Blog post '{b.get('title')}': Published as draft"})
        except Exception as e:
            logs.append({"agent": "executor", "text": f"Blog post FAILED for '{b.get('title')}': {e}"})

    logs.append({"agent": "orchestrator", "text": "Execution complete. All tasks finished."})
    ctx["state"] = "complete"; save_context(session_id, ctx)
    return logs
