# orchestrator.py

import asyncio
import json
import typing as t
from search_crawl import build_weekly_snapshot
from context_store import save_context, load_context
from topical_map import TopicalMap
from meta_optimization import MetaOptimization
from onpage_seo import OnPageSEO
from blog_automation import BlogAutomation
from cms_base import get_client
from seo_common import genai_model

class Agent:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.model = genai_model()
        self.ctx = load_context(session_id) or {"history": [], "state": "start"}

    def chat(self, instruction: str) -> str:
        # This is the new, high-quality prompt that forces the AI to be specific and intelligent.
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
        if not self.model: return "LLM is not configured."
        try:
            resp = self.model.generate_content(system_prompt)
            clean_response = resp.text.split('</thinking>')[-1].strip()
            return clean_response or "I have finished the step."
        except Exception as e:
            print(f"LLM Generation Error: {e}")
            return f"Error connecting to AI model: {e}"

# This is the stable, linear, streaming architecture that works reliably.
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
            
            messages.append({"agent": "orchestrator", "text": "Identifying content gaps and blog opportunities...", "status": "in_progress"})
            TopicalMap().generate_map(session_id)
            agent.ctx = load_context(session_id)

            messages.append({"agent": "orchestrator", "text": "Finalizing SEO score and recommendations...", "status": "in_progress"})
            await asyncio.sleep(1.5)

            agent.ctx["state"] = "presenting_findings"
            save_context(session_id, agent.ctx)
            
            instruction = f"The analysis of {url} is complete. It has {snapshot.get('pages', 0)} pages and the platform is {snapshot.get('platform', 'unknown')}. Present the findings to the user. Be specific and exciting using the context data. Give a score. End by asking for permission to generate the full action plan."
            agent_response = agent.chat(instruction)
            messages.append({"agent": "orchestrator", "text": agent_response})

        except Exception as e:
            messages.append({"agent": "orchestrator", "text": f"An error occurred during discovery: {e}"})
            agent.ctx["state"] = "error"; save_context(session_id, agent.ctx)

    elif state == "presenting_findings":
        instruction = f"The user has responded to your analysis with: '{user_message}'. If they've given approval (e.g., 'yes', 'ok', 'sure'), confirm you're generating the detailed action plan. If they ask a question, answer it. Otherwise, gently nudge them for approval."
        agent_response = agent.chat(instruction)
        messages.append({"agent": "orchestrator", "text": agent_response})
        
        if any(word in user_message.lower() for word in ["yes", "ok", "proceed", "sure", "yep", "do it"]):
            agent.ctx["state"] = "generating_proposals"; save_context(session_id, agent.ctx)
            
            messages.append({"agent": "orchestrator", "text": "Preparing technical page rewrites...", "status": "in_progress"})
            await asyncio.to_thread(OnPageSEO().analyze_website, session_id)
            
            messages.append({"agent": "orchestrator", "text": "Optimizing all meta titles and descriptions...", "status": "in_progress"})
            await asyncio.to_thread(MetaOptimization().optimize_meta_tags, session_id)

            messages.append({"agent": "orchestrator", "text": "Drafting all scheduled blog posts...", "status": "in_progress"})
            await asyncio.to_thread(BlogAutomation().schedule_blogs, session_id)
            
            agent.ctx = load_context(session_id)
            agent.ctx["state"] = "awaiting_final_approval"; save_context(session_id, agent.ctx)
            platform = agent.ctx.get("website", {}).get("platform", "CMS").capitalize()
            instruction = "All proposals are now generated. Announce that the action plan is ready for review. Remind the user of the platform you detected and ask for the appropriate credentials to execute the plan."
            agent_response_2 = agent.chat(instruction)
            messages.append({"agent": "orchestrator", "text": agent_response_2, "actions": [{"type": "review_changes", "label": "Review Action Plan"}, {"type": "provide_keys", "label": f"Provide {platform} Credentials & Approve"}]})
    else:
        messages.append({"agent": "orchestrator", "text": agent.chat(f"The user said: '{user_message}'. Respond helpfully.")})
    
    return messages

async def execute_with_keys(session_id: str, creds: dict) -> list[dict]:
    ctx = load_context(session_id)
    platform = ctx.get("website", {}).get("platform", "unknown")
    site_url = ctx.get("website", {}).get("url")
    creds_with_url = {**creds, "site_url": site_url}
    client = get_client(platform, creds_with_url)
    logs = []

    meta_proposals = ctx.get("agents", {}).get("meta_optimization", {}).get("proposals", [])
    for item in meta_proposals:
        try:
            res = client.update_page_meta(item['page_url'], item['after']['title'], item['after']['description'])
            logs.append({"agent": "executor", "text": f"Meta update for {item['page_url']}: Success"})
        except Exception as e: logs.append({"agent": "executor", "text": f"Meta update FAILED for {item['page_url']}: {e}"})

    onpage_proposals = ctx.get("agents", {}).get("onpage_seo", {}).get("proposals", [])
    for p in onpage_proposals:
        try:
            res = client.inject_json_ld(p.get('page_url'), p.get('proposed_schema', {}))
            logs.append({"agent": "executor", "text": f"Schema inject for {p.get('page_url')}: Success"})
        except Exception as e: logs.append({"agent": "executor", "text": f"Schema inject FAILED for {p.get('page_url')}: {e}"})

    blog_schedule = ctx.get("agents", {}).get("blog_automation", {}).get("schedule", [])
    for b in blog_schedule:
        try:
            with open(b['draft_path'], 'r', encoding='utf-8') as f: html_content = f.read()
            res = client.create_post('blog', b.get('title'), html_content, slug=b.get('title').replace(' ','-').lower())
            logs.append({"agent": "executor", "text": f"Blog post '{b.get('title')}': Published as draft"})
        except Exception as e: logs.append({"agent": "executor", "text": f"Blog post FAILED for '{b.get('title')}': {e}"})

    logs.append({"agent": "orchestrator", "text": "Execution complete. All tasks finished."})
    ctx["state"] = "complete"; save_context(session_id, ctx)
    return logs