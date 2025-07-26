# src/backend/agents/sous_chef_agent.py

import warnings
import logging
import os

import sys
import uuid
import json
from typing import Dict, List
import google.generativeai as genai
from dotenv import load_dotenv
from pyprojroot.here import here
from google.adk.agents import Agent
from google.adk.tools import ToolContext
from google.adk.tools.base_tool import BaseTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.genai.types import Content, Part
import asyncio
from loguru import logger
import time

# Add project root to path for imports
project_root = here()
sys.path.insert(0, str(project_root))

from tools.timer_tool import parse_timer_duration, timer_tool, set_custom_timer, web_timer_tool, check_timer_completion

# warnings.filterwarnings("ignore")
# logging.getLogger("google").setLevel(logging.ERROR)
# logging.getLogger("google.adk").setLevel(logging.ERROR)
# logging.getLogger("google.generativeai").setLevel(logging.ERROR)

# logger.remove()
# logger.add("src/agents/sous_chef_agent.log", rotation="500 MB", level="DEBUG")

# if os.path.exists("src/agents/sous_chef_agent.log"):
#     with open("src/agents/sous_chef_agent.log", "w") as f:
#         f.truncate(0)

load_dotenv(dotenv_path=here(".env"))
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set.")
genai.configure(api_key=api_key)

MODEL = "gemini-1.5-flash" # TODO: Update to 2.5
COMPLETION_PHRASE = "The recipe is finished."
APP_NAME = "cooking_assistant"
USER_ID = "test_user"

# Default recipe for CLI testing
DEFAULT_RECIPE = {
    "name": "Tiktok Baked Feta Pasta",
    "steps": {
        "1": "Preheat the oven to 400°F (200°C).",
        "2": "In a baking dish, toss cherry tomatoes with olive oil.",
        "3": "Place a block of feta in the center of the dish and drizzle it with more olive oil.",
        "4": "Put the dish in the oven. When ready to time the baking, say 'next' again to start a 20-second timer.",
    },
}


def run_countdown_timer(time_in_seconds: int) -> dict:
    """CLI countdown implementation"""
    logger.info(f"🛠️ COUNTDOWN STARTED: {time_in_seconds} seconds")
    try:
        print(f"⏰ Starting {time_in_seconds} second timer...")

        for remaining in range(time_in_seconds, 0, -1):
            logger.info(f"⏰ Timer: {remaining} seconds remaining...")
            print(f"⏰ {remaining}...")
            time.sleep(1)

        logger.info("🔔 Timer completed! Time's up!")
        print("🔔 Time's up!")

        return {
            "status": "success",
            "message": f"Timer completed after {time_in_seconds} seconds.",
        }
    except Exception as e:
        logger.error(f"❌ Unexpected error in countdown: {e}")
        return {"status": "error", "message": f"Countdown error: {str(e)}"}
      

def exit_loop(tool_context: ToolContext):
    """Recipe completion handler"""
    logger.info(f"Exit loop triggered by {tool_context.agent_name}")
    tool_context.state["recipe_completed"] = True
    tool_context.actions.escalate = True
    return {"status": "success", "message": "Recipe completed, exiting loop."}


def wait_for_user_confirmation(tool_context: ToolContext) -> dict:
    return {"status": "waiting", "message": "Please type 'next' to continue."}


class RecipeManagerTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="recipe_manager", description="Manages recipe steps"
        )

    def get_current_step(self, tool_context: ToolContext) -> dict:
        recipe_steps = tool_context.state.get("recipe_steps", {})
        current_index = tool_context.state.get("step_index", 0)

        if not recipe_steps:
            return {"step": "No recipe loaded", "step_number": 0, "is_complete": True}

        step_keys = sorted([int(k) for k in recipe_steps.keys()])

        if current_index >= len(step_keys):
            tool_context.state["recipe_completed"] = True
            return {
                "step": COMPLETION_PHRASE,
                "step_number": "complete",
                "is_complete": True,
            }

        current_step_key = str(step_keys[current_index])
        current_step_text = recipe_steps[current_step_key]

        tool_context.state["current_step_text"] = current_step_text
        tool_context.state["current_step_number"] = current_index + 1

        return {
            "step": current_step_text,
            "step_number": current_index + 1,
            "is_complete": False,
        }

    def advance_step(self, tool_context: ToolContext) -> dict:
        current_index = tool_context.state.get("step_index", 0)
        recipe_steps = tool_context.state.get("recipe_steps", {})
        step_keys = sorted([int(k) for k in recipe_steps.keys()])

        new_index = current_index + 1
        tool_context.state["step_index"] = new_index

        if new_index >= len(step_keys):
            tool_context.state["recipe_completed"] = True

        return {"status": "success", "message": f"Advanced to step {new_index + 1}"}


# Unified recipe tool and agent
recipe_tool = RecipeManagerTool()

sous_chef_agent = Agent(
    name="SousChefAgent",
    model=MODEL,
    tools=[
        recipe_tool.get_current_step,
        recipe_tool.advance_step,
        parse_timer_duration,
        web_timer_tool,
        set_custom_timer,
        wait_for_user_confirmation,
        exit_loop,
    ],
    instruction="""You are a friendly Sous Chef helping users cook step by step.

WORKFLOW:
1. First interaction: Greet, get_current_step, present step, wait_for_user_confirmation
2. User says 'next': advance_step, get_current_step, present step, handle timers if needed
3. Timer handling: parse_timer_duration → web_timer_tool
4. Completion: get_current_step returns completion phrase → exit_loop

TIMER WORKFLOW:
- Parse timer duration with parse_timer_duration
- Say: "I'll start a [duration] timer when ready. Type 'start' to begin, or different duration."
- User "start": Call web_timer_tool immediately
- Custom duration: Call set_custom_timer, wait for "start"

Keep responses encouraging and concise.""",
)


class CookingAgentHandler:
    def __init__(self, app_name: str = APP_NAME, memory_service=None, session_service=None):
        self.app_name = app_name
        self.session_service = session_service or InMemorySessionService()
        self.memory_service = memory_service or InMemoryMemoryService()
        self.active_runners: Dict[str, Runner] = {}

    async def start_cooking_session(self, recipe_data: dict) -> dict:
        """Start a new cooking session with recipe data"""
        session_id = str(uuid.uuid4())
        
        initial_state = {
            "step_index": 0,
            "recipe_completed": False,
            "recipe_name": recipe_data["name"],
            "recipe_steps": recipe_data["steps"],
            "timer_active": False,
        }

        session = await self.session_service.create_session(
            app_name=self.app_name,
            user_id="web_user",
            session_id=session_id,
            state=initial_state,
        )

        runner = Runner(
            agent=sous_chef_agent,
            session_service=self.session_service,
            app_name=self.app_name,
        )
        self.active_runners[session_id] = runner

        # Initial greeting
        greeting_content = Content(
            parts=[Part(text="Hello, let's start cooking!")], role="user"
        )

        response_text = ""
        waiting_for_user = False

        async for event in runner.run_async(
            user_id="web_user", session_id=session_id, new_message=greeting_content
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text
                    elif (
                        part.function_call
                        and part.function_call.name == "wait_for_user_confirmation"
                    ):
                        waiting_for_user = True

            if event.is_final_response():
                break

        updated_session = await self.session_service.get_session(
            app_name=self.app_name, user_id="web_user", session_id=session_id
        )

        return {
            "session_id": session_id,
            "message": response_text,
            "waiting_for_user": waiting_for_user,
            "recipe_completed": updated_session.state.get("recipe_completed", False),
            "session_state": updated_session.state,
        }

    async def handle_interaction(self, session_id: str, message: str) -> dict:
        """Handle user interaction with existing session"""
        runner = self.active_runners.get(session_id)
        if not runner:
            raise ValueError("Cooking session not found")

        # Check timer completion
        session = await self.session_service.get_session(
            app_name=self.app_name, user_id="web_user", session_id=session_id
        )

        timer_completion_msg = check_timer_completion(session.state)

        user_content = Content(parts=[Part(text=message)], role="user")

        response_text = ""
        waiting_for_user = False

        async for event in runner.run_async(
            user_id="web_user", session_id=session_id, new_message=user_content
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text
                    elif (
                        part.function_call
                        and part.function_call.name == "wait_for_user_confirmation"
                    ):
                        waiting_for_user = True

            if event.is_final_response():
                break

        updated_session = await self.session_service.get_session(
            app_name=self.app_name, user_id="web_user", session_id=session_id
        )

        recipe_completed = updated_session.state.get("recipe_completed", False)

        # Prepend timer completion message
        if timer_completion_msg:
            response_text = timer_completion_msg + "\n\n" + response_text

        # Cleanup completed sessions
        if recipe_completed and session_id in self.active_runners:
            await self.memory_service.add_session_to_memory(updated_session)
            del self.active_runners[session_id]

        return {
            "session_id": session_id,
            "message": response_text,
            "waiting_for_user": waiting_for_user,
            "recipe_completed": recipe_completed,
            "session_state": updated_session.state,
        }

    async def get_session_status(self, session_id: str) -> dict:
        """Get current session status"""
        session = await self.session_service.get_session(
            app_name=self.app_name, user_id="web_user", session_id=session_id
        )

        if not session:
            raise ValueError("Session not found")

        return {
            "session_id": session_id,
            "recipe_name": session.state.get("recipe_name"),
            "current_step": session.state.get("current_step_number", 0),
            "recipe_completed": session.state.get("recipe_completed", False),
            "session_state": session.state,
        }

    async def end_session(self, session_id: str) -> dict:
        """End a cooking session"""
        if session_id in self.active_runners:
            del self.active_runners[session_id]

        return {"message": "Cooking session ended", "session_id": session_id}


# CLI main function
async def main():
    """CLI test function"""
    handler = CookingAgentHandler("sous_chef_test_app")
    
    print("🍳 Starting CLI Sous Chef Test")
    print("=" * 60)
    
    # Start cooking with default recipe
    result = await handler.start_cooking_session(DEFAULT_RECIPE)
    session_id = result["session_id"]
    
    print(f"\n🍴 Sous Chef: {result['message']}")
    
    iteration_count = 0
    max_iterations = 20

    while iteration_count < max_iterations:
        iteration_count += 1
        
        user_input = input(
            "\n⏭️ Type your response (or 'quit' to exit): "
            if result.get("waiting_for_user")
            else "\n💬 Type your message (or 'quit' to exit): "
        )
        
        if user_input.lower() == "quit":
            break
            
        try:
            result = await handler.handle_interaction(session_id, user_input)
            
            # Handle CLI timer
            if "timer_tool" in result.get("message", ""):
                # Extract duration and run countdown
                import re
                duration_match = re.search(r'(\d+).*?second', result["message"])
                if duration_match:
                    duration = int(duration_match.group(1))
                    run_countdown_timer(duration)
                    print("\n⏭️ Timer complete! Type 'next' to continue.")
            
            print(f"\n🍴 Sous Chef: {result['message']}")
            
            if result.get("recipe_completed"):
                print("🎉 Recipe completed! Enjoy your meal!")
                break
                
        except Exception as e:
            print(f"❌ Error: {e}")
            break


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting.")