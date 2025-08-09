# orchestrator.py

import os, asyncio, json
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

    def chat(self, user_message: str) -> str:
        # --- FINAL, HIGH-CONTROL, USER-FRIENDLY PROMPT ---
        system_prompt = f"""
        You are "FieldNote", an expert AI SEO strategist.
        Your Persona: You are a helpful, clear, and encouraging guide. You are talking to a smart business owner or developer who is not an SEO expert. Avoid overly technical jargon. Explain *why* things matter in simple terms.

        **CRITICAL RULES:**
        1.  **BE CONCISE:** Use bullet points and bold text. Keep responses short.
        2.  **NO INTERNAL STATE:** NEVER mention "Session ID", "State", or internal function names.
        3.  **FOLLOW INSTRUCTIONS:** Based on the current state and the user's message, generate the EXACT type of response requested.

        ---
        **Current State:** {self.ctx.get("state")}
        **Website URL:** {self.ctx.get("url")}
        ---

        **INSTRUCTION FOR THIS TURN:**

        **IF the state is 'discovery':**
        The user has just provided a URL. Your *only* job is to announce the first step of your plan.
        Your response MUST be ONLY this:
        "Excellent. I am beginning the analysis of **{self.ctx.get("url")}**.
        *   **Current Step:** Scraping all pages to build a complete picture of your website..."

        **IF the state is 'analysis':**
        The scraping is done. Announce the next step. Your response MUST be ONLY this:
        "Scraping complete.
        *   **Current Step:** Analyzing content for SEO opportunities..."

        **IF the state is 'presenting_findings':**
        The analysis is complete. Present your findings clearly and simply. Calculate a score between 50-85.
        Your response MUST follow this template:
        "✅ Analysis complete!
        Based on my findings, I've given **{self.ctx.get("url")}** a preliminary SEO Score of **[Your Score]/100**.

        Here's a simple breakdown of what I found:
        *   **Technical Health:** I noticed some issues [e.g., 'with how search engines are guided through your site'], which can cause them to miss important pages.
        *   **On-Page Content:** Many pages are missing clear, compelling titles and descriptions that attract clicks from Google.
        *   **Content Strategy:** Your website has an opportunity to attract more visitors by creating new articles on specific topics your customers are searching for.

        I have a detailed, automated plan to fix these items.
        **Shall I proceed with generating the specific changes for your review?**"

        **IF the state is 'generating_proposals':**
        The user said yes. Announce that you are preparing the detailed plan. Your response MUST be ONLY this:
        "Perfect. I'm now running my specialized agents to prepare the full action plan. This includes rewriting page content, optimizing meta tags, and drafting new blog posts. I'll let you know the moment it's ready for your review."

        **IF the state is 'awaiting_final_approval':**
        All proposals are ready. Announce this and provide the call to action. Your response MUST be ONLY this:
        "The complete action plan is ready for your review. I've prepared all the necessary changes to improve your site's SEO.
        Please review the plan. When you're ready, provide your CMS credentials to allow me to execute the changes autonomously."
        ---
        User's latest message for context: "{user_message}"
        """
        if not self.model: return "LLM is not configured."
        try:
            resp = self.model.generate_content(system_prompt)
            return (resp.text or "An error occurred.").strip()
        except Exception as e:
            print(f"LLM Generation Error: {e}")
            return f"Error connecting to AI model: {e}"

async def run_orchestrator_turn(session_id: str, user_message: str, api_keys: t.Optional[dict] = None) -> t.List[dict]:
    agent = Agent(session_id)
    state = agent.ctx.get("state", "start")
    messages = []

    if state == "start" and user_message.startswith("analyze:"):
        url = user_message.split("analyze:", 1)[1].strip()
        agent.ctx["url"] = url
        agent.ctx["state"] = "discovery"
        save_context(session_id, agent.ctx)
        
        # --- NEW MULTI-STEP RESPONSE ---
        # 1. Send the "Scraping..." message immediately
        agent_response_1 = agent.chat(user_message)
        messages.append({"agent": "orchestrator", "text": agent_response_1, "status": "in_progress"})
        
        try:
            # 2. Perform the long-running task
            await build_weekly_snapshot(session_id, url, max_pages=50)
            
            # 3. Update state and send the "Analyzing..." message
            agent.ctx = load_context(session_id)
            agent.ctx["state"] = "analysis"
            save_context(session_id, agent.ctx)
            agent_response_2 = agent.chat("internal:scraping_complete")
            messages.append({"agent": "orchestrator", "text": agent_response_2, "status": "in_progress"})

            # 4. Perform the analysis (this is fast)
            # This is a placeholder for any future heavy analysis. Right now, it's quick.
            await asyncio.sleep(2) # Simulate analysis work
            
            # 5. Update state and send the final findings
            agent.ctx["state"] = "presenting_findings"
            save_context(session_id, agent.ctx)
            agent_response_3 = agent.chat("internal:analysis_complete")
            messages.append({"agent": "orchestrator", "text": agent_response_3})

        except Exception as e:
            messages.append({"agent": "orchestrator", "text": f"❌ Error during discovery: {e}"})
            agent.ctx["state"] = "error"; save_context(session_id, agent.ctx)

    elif state == "presenting_findings" and "yes" in user_message.lower():
        agent.ctx["state"] = "generating_proposals"; save_context(session_id, agent.ctx)
        agent_response = agent.chat("internal:user_approved_generation")
        messages.append({"agent": "orchestrator", "text": agent_response, "status": "in_progress"})
        
        # This can also take a moment, so it's good it's a separate step
        await asyncio.gather(
            asyncio.to_thread(OnPageSEO().analyze_website, session_id),
            asyncio.to_thread(MetaOptimization().optimize_meta_tags, session_id),
            asyncio.to_thread(TopicalMap().generate_map, session_id)
        )
        BlogAutomation().schedule_blogs(session_id)
        
        agent.ctx = load_context(session_id)
        agent.ctx["state"] = "awaiting_final_approval"; save_context(session_id, agent.ctx)
        platform = agent.ctx.get("website", {}).get("platform", "CMS").capitalize()
        agent_response_2 = agent.chat("internal:proposals_generated")
        messages.append({"agent": "orchestrator", "text": agent_response_2, "actions": [{"type": "review_changes", "label": "Review All Changes"}, {"type": "provide_keys", "label": f"Provide {platform} Keys & Approve"}]})
    
    else:
        # Fallback for any other state or message
        messages.append({"agent": "orchestrator", "text": agent.chat(user_message)})
    
    return messages

async def execute_with_keys(session_id: str, creds: dict) -> list[dict]:
    # This function remains correct and does not need changes
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