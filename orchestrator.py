# orchestrator.py

import os, asyncio, json, datetime
import typing as t
import google.generativeai as genai

from search_crawl import build_weekly_snapshot
from context_store import save_context, load_context
from topical_map import TopicalMap
from meta_optimization import MetaOptimization
from onpage_seo import OnPageSEO
from blog_automation import BlogAutomation
from cms_tools import get_cms_tool
from dotenv import load_dotenv

load_dotenv()
try:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
except KeyError:
    raise RuntimeError("Error: GEMINI_API_KEY environment variable not set.")

class Agent:
    """A true LLM-powered agent that uses tools to achieve a goal."""
    def __init__(self, session_id: str, model_name: str = "gemini-2.5-pro"):
        self.session_id = session_id
        self.model = genai.GenerativeModel(model_name)
        self.ctx = load_context(session_id) or {"history": [], "state": "start"}
        self.tools = {
            "build_snapshot": build_weekly_snapshot,
            "generate_onpage_proposals": OnPageSEO().analyze_website,
            "generate_meta_proposals": MetaOptimization().optimize_meta_tags,
            "generate_topical_map": TopicalMap().generate_map,
            "schedule_blog_drafts": BlogAutomation().schedule_blogs,
            "get_cms_tool": get_cms_tool,
        }
    def _save_memory(self, user_text: str, agent_text: str):
        """Save the conversation turn to context file."""
        self.ctx["history"].append({"user": user_text, "agent": agent_text})
        save_context(self.session_id, self.ctx)

    def chat(self, user_message: str) -> str:
        """The main reasoning loop of the agent."""

        system_prompt = f"""
        You are "FieldNote", an expert, autonomous AI SEO strategist.
        Your goal is to perform a complete SEO audit and optimization for the user's website.
        You must operate in a step-by-step manner, clearly communicating your actions to the user.

        CONTEXT:
        -Session ID: {self.session_id}
        -Current State: {self.ctx.get("state", "start")}
        -Website URL: {self.ctx.get("url", "not set")}
        -Conversation History: {json.dumps(self.ctx['history'][-3:], ensure_ascii=False)}

        Based on the user's message below and the current state, decide on the *single next thing* to say to the user.
        Your response should be conversational, informative, and guide the user through the process.
        Explain what you are about to do, or what you have just done.

        User's latest message: "{user_message}"
        """
        response = self.model.generate_text(system_prompt)
        agent_response_text = response.text.strip()

        self._save_memory(user_message, agent_response_text)
        return agent_response_text

async def run_orchestrator_turn(session_id: str, user_message: str, api_keys: t.Optional[dict] = None) -> t.List[dict]:
    """
    Manages the conversational flow by calling the Agent and its tools.
    This function now orchestrates the agent's thinking and acting phases.
    """
    agent = Agent(session_id)
    state = agent.ctx.get("state", "start")
    messages = []

    if state == "start" and user_message.startswith("analyze:"):
        url = user_message.split("analyze:", 1)[1].strip()
        agent.ctx["url"] = url
        agent.ctx["state"] = "discovery"
        save_context(session_id, agent.ctx)

        # 1. Agent "thinks" and generates it's opening plan
        agent_response = agent.chat(f" The user wants to analyze {url}. Announce your multi-step discovery plan.")
        messages.append({"agent": "orchestrator", "text": agent_response})

        # 2. Agent "acts" by building a snapshot tool
        try:
            await agent.tools["build_snapshot"](session_id, url, max_pages=50)
            agent.ctx = load_context(session_id)
            agent.ctx["state"] = "analysis"
            save_context(session_id, agent.ctx)
            
            # 3. Agent "thinks" again to anounce completion and next steps
            agent_response_2 = agent.chat("I have just finished the discovery phase. Now, analyze the findings, calculate an SEO score, and ask the user for permission to generate detailed fixes.")
            messages.append({"agent": "orchestrator", "text": agent_response_2})
        except Exception as e:
            error_message = f"❌ An Error occurred during discovery: {e}"
            messages.append({"agent": "orchestrator", "text": error_message})
            agent.ctx["state"] = "error"
            save_context(session_id, agent.ctx)

    # --- User Approves Fix Generation ---
    elif state == "analysis" and "yes" in user_message.lower():
        agent.ctx["state"] = "execution"
        save_context(session_id, agent.ctx)

        # 1. Agent announces it's running the specialist tools
        agent_response = agent.chat("The user has approved generating the fixes. Announce that you are running the SEO agents to prepare the changes.")
        messages.append({"agent": "orchestrator", "text": agent_response})

        # 2. Agent "acts" by calling all the generation tools
        agent.tools["generate_onpage_proposals"](session_id)
        agent.tools["generate_meta_proposals"](session_id)
        tm_results = agent.tools["generate_topical_map"](session_id)
        blog_topics = [t['title'] for c in tm_results.get("clusters", {}).values() for t in c.get("subtopics", [])][:7]
        agent.tools["schedule_blog_drafts"](session_id, days=len(blog_topics), generate_drafts=True)

        # 3. Agent announces completion asks for final review/keys
        agent.ctx = load_context(session_id)
        agent.ctx["state"] = "awaiting_final_approval"
        save_context(session_id, agent.ctx)

        platform = agent.ctx.get("website", {}).get("platform", "CMS").capitalize()
        agent_response_2 = agent.chat(f"All proposals are generated. Announce this, and tell the user they need to provide final approval and API keys for their {platform} site. Provide actions to review changes and provide keys.")
        messages.append({
            "agent": "orchestrator", 
            "text": agent_response_2,
            "actions": [
                {"type": "review_changes", "label": "Review All Changes"},
                {"type": "provide_keys", "label": "Provide {platform} Keys & Approve"}
            ]
        })
    # ---State 3: Execute Changes with API Keys---
    elif state == "awaiting_final_approval" and user_message == "internal:execute_with_keys":
        platform = agent.ctx.get("website", {}).get("platform")
        site_url = agent.ctx.get("website", {}).get("url")
        agent.ctx["state"] = "executing"
        save_context(session_id, agent.ctx)

        agent_response = agent.chat(f"User has provided API keys for {platform}. Announce that you are deploying the changes irreversibly.")
        messages.append({"agent": "orchestrator", "text": agent_response})

        try:
            tool = agent.tools["get_cms_tool"](platform, site_url, api_keys)

            onpage_result = tool.apply_onpage_changes(agent.ctx['agents']['onpage_seo']['proposals'])
            messages.append({"agent": "OnPageSEO", "text": onpage_result['message']})
            meta_result = tool.apply_meta_changes(agent.ctx['agents']['meta_optimization']['proposals'])
            messages.append({"agent": "MetaOptimizer", "text": meta_result['message']})
            blog_result = tool.publish_blog_posts(agent.ctx['agents']['blog_automation']['schedule'])
            messages.append({"agent": "BlogAutomator", "text": blog_result['message']})

            agent.ctx["state"] = "complete"
            save_context(session_id, agent.ctx)
            agent_response_final = agent.chat(f"All tasks are complete. Announce that the optimization is done.")
            messages.append({"agent": "orchestrator", "text": agent_response_final}) 
        except Exception as e:
            messages.append({"agent": "orchestrator", "text": f"❌ Execution failed: {e}"})
            agent.ctx["state"] = "error"
            save_context(session_id, agent.ctx)
    else:
        # Default response if the state is not recognized
        agent_response = agent.chat(user_message)
        messages.append({"agent": "orchestrator", "text": agent_response})

    return messages
