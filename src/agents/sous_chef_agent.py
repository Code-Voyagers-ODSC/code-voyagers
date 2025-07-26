# agents/sous_chef_agent.py - Updated to support dynamic recipes

import warnings
import logging
import os
import sys
import google.generativeai as genai
from dotenv import load_dotenv
from pyprojroot.here import here
from google.adk.agents import Agent
from google.adk.tools import ToolContext
from google.adk.tools.base_tool import BaseTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
import asyncio
from loguru import logger
import time
from typing import Dict, Optional

# Add project root to path for imports
project_root = here()
sys.path.insert(0, str(project_root))

warnings.filterwarnings("ignore")
logging.getLogger("google").setLevel(logging.ERROR)
logging.getLogger("google.adk").setLevel(logging.ERROR)
logging.getLogger("google.generativeai").setLevel(logging.ERROR)

logger.remove()
logger.add("src/sous_chef_agent/sous_chef_agent.log", rotation="500 MB", level="DEBUG")

if os.path.exists("src/sous_chef_agent/sous_chef_agent.log"):
    with open("src/sous_chef_agent/sous_chef_agent.log", "w") as f:
        f.truncate(0)

load_dotenv(dotenv_path=here(".env"))
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set.")
genai.configure(api_key=api_key)

MODEL = "gemini-2.5-flash"
COMPLETION_PHRASE = "The recipe is finished."
APP_NAME = "sous_chef_test_app"
USER_ID = "test_user"


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


class RecipeManagerTool(BaseTool):
    """Recipe progress manager"""

    def __init__(self, steps: dict):
        super().__init__(name="recipe_manager", description="Manages recipe steps")
        self._steps = steps
        self._step_keys = sorted(steps.keys())

    def get_current_step(self, tool_context: ToolContext) -> dict:
        current_index = tool_context.state.get("step_index", 0)

        if current_index >= len(self._step_keys):
            tool_context.state["recipe_completed"] = True
            return {
                "step": COMPLETION_PHRASE,
                "step_number": "complete",
                "is_complete": True,
            }

        current_step_key = self._step_keys[current_index]
        current_step_text = self._steps[current_step_key]
        tool_context.state["current_step_text"] = current_step_text
        tool_context.state["current_step_number"] = current_index + 1

        return {
            "step": current_step_text,
            "step_number": current_index + 1,
            "is_complete": False,
        }

    def advance_step(self, tool_context: ToolContext) -> dict:
        current_index = tool_context.state.get("step_index", 0)
        new_index = current_index + 1
        tool_context.state["step_index"] = new_index

        if new_index >= len(self._step_keys):
            tool_context.state["recipe_completed"] = True

        return {"status": "success", "message": f"Advanced to step {new_index + 1}."}


def wait_for_user_confirmation(tool_context: ToolContext) -> dict:
    return {"status": "waiting", "message": "Please type 'next' to continue."}


def parse_timer_duration(tool_context: ToolContext, text: str) -> dict:
    """Parse timer duration from text"""
    import re
    
    # Look for various timer patterns
    patterns = [
        (r'(\d+)\s*minutes?', 60),  # minutes
        (r'(\d+)\s*mins?', 60),      # abbreviated minutes
        (r'(\d+)\s*seconds?', 1),    # seconds
        (r'(\d+)\s*secs?', 1),       # abbreviated seconds
        (r'(\d+)\s*hours?', 3600),  # hours
        (r'(\d+)\s*hrs?', 3600),    # abbreviated hours
    ]
    
    total_seconds = 0
    for pattern, multiplier in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            total_seconds += int(match.group(1)) * multiplier
    
    if total_seconds > 0:
        return {"duration": total_seconds, "status": "success"}
    return {"duration": 0, "status": "not_found"}


def timer_tool(tool_context: ToolContext, time_in_seconds: int) -> dict:
    """Start a timer"""
    return run_countdown_timer(time_in_seconds)


def set_custom_timer(tool_context: ToolContext, duration: int) -> dict:
    """Set a custom timer duration"""
    tool_context.state["custom_timer_duration"] = duration
    return {"status": "custom_timer_set", "duration": duration}


def create_sous_chef_agent(recipe_dict: Dict[str, any]) -> tuple[Agent, RecipeManagerTool]:
    """
    Create a sous chef agent with a specific recipe.
    
    Args:
        recipe_dict: Dictionary with 'name' and 'steps' keys
        
    Returns:
        Tuple of (agent, recipe_tool)
    """
    recipe_tool = RecipeManagerTool(recipe_dict["steps"])
    
    sous_chef_agent = Agent(
        name="SousChefAgent",
        model=MODEL,
        tools=[
            recipe_tool.get_current_step,
            recipe_tool.advance_step,
            parse_timer_duration,
            timer_tool,
            set_custom_timer,
            wait_for_user_confirmation,
            exit_loop,
        ],
        instruction=f"""You are a friendly Sous Chef helping users cook {recipe_dict["name"]} step by step.

WORKFLOW:
1. First interaction: Greet, get_current_step, present step, wait_for_user_confirmation
2. User says 'next': advance_step, get_current_step, present step, handle timers if needed
3. Timer workflow: parse_timer_duration → offer timer → user "start" → timer_tool
4. Completion: If get_current_step returns completion phrase, call exit_loop

TIMER RULES:
- Use parse_timer_duration to extract duration from the current step
- Say: "I'll start a [duration] timer when ready. Type 'start' to begin."
- User "start": Call timer_tool immediately
- Custom duration: Call set_custom_timer, wait for "start"

Keep responses concise and helpful. Be encouraging and friendly!""",
    )
    
    return sous_chef_agent, recipe_tool


async def run_sous_chef_session(recipe_dict: Dict[str, any], session_id: Optional[str] = None):
    """
    Run a complete sous chef cooking session with the given recipe.
    
    Args:
        recipe_dict: Dictionary with 'name' and 'steps' keys
        session_id: Optional session ID for tracking
    """
    # Create agent with the recipe
    sous_chef_agent, recipe_tool = create_sous_chef_agent(recipe_dict)
    
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        state={"step_index": 0, "recipe_completed": False},
        session_id=session_id
    )

    runner = Runner(
        agent=sous_chef_agent, 
        session_service=session_service, 
        app_name=APP_NAME
    )
    
    current_query_content = Content(
        parts=[Part(text="Hello, let's start cooking!")], 
        role="user"
    )

    iteration_count = 0
    max_iterations = 50  # Increased for longer recipes

    while iteration_count < max_iterations:
        iteration_count += 1
        final_response_text = ""
        waiting_for_user = False
        timer_called = False
        timer_duration = 0

        async for event in runner.run_async(
            user_id=USER_ID, 
            session_id=session.id, 
            new_message=current_query_content
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        final_response_text += part.text
                    elif part.function_call:
                        if part.function_call.name in ["wait_for_user_confirmation"]:
                            waiting_for_user = True
                        elif part.function_call.name == "timer_tool":
                            timer_called = True
                            if "time_in_seconds" in part.function_call.args:
                                timer_duration = part.function_call.args["time_in_seconds"]

            if event.is_final_response():
                print(f"\n🍴 Sous Chef: {final_response_text}")

                if timer_called and timer_duration > 0:
                    # Timer is handled in the timer_tool function
                    print("\n⏭️ Timer complete! Type 'next' to continue.")

                if (
                    COMPLETION_PHRASE in final_response_text
                    or "Congratulations" in final_response_text
                ):
                    print("🎉 Recipe completed! Enjoy your meal!")
                    return
                break

        user_input = input(
            "\n⏭️ Type your response (or 'quit' to exit): "
            if waiting_for_user
            else "\n💬 Type your message (or 'quit' to exit): "
        )
        if user_input.lower() == "quit":
            break
        current_query_content = Content(parts=[Part(text=user_input)], role="user")


# For testing with the integrated system
async def test_with_suggester():
    """Test function that gets a recipe from suggester and runs sous chef"""
    from agents.suggester_agent import smart_recipe_search_handler, extract_sous_chef_dict
    
    # Get a recipe from the suggester
    ingredients = ["chicken", "pasta", "garlic"]
    print(f"🔍 Searching for recipes with: {', '.join(ingredients)}")
    
    recipe_response = await smart_recipe_search_handler(ingredients)
    
    if not recipe_response.recipes:
        print("No recipes found!")
        return
    
    # Use the first recipe
    recipe = extract_sous_chef_dict(recipe_response, 0)
    print(f"\n🍳 Selected recipe: {recipe['name']}")
    print(f"📝 Number of steps: {len(recipe['steps'])}")
    print("=" * 60)
    
    # Run the sous chef session
    await run_sous_chef_session(recipe)


# Example of how to run with a custom recipe
async def main():
    # Option 1: Test with a hardcoded recipe
    test_recipe = {
        "name": "Quick Garlic Pasta",
        "steps": {
            "1": "Fill a large pot with water and bring to a boil",
            "2": "Add pasta to boiling water and cook for 8-10 minutes",
            "3": "While pasta cooks, mince 3 cloves of garlic",
            "4": "Heat olive oil in a pan over medium heat",
            "5": "Add garlic to the pan and cook for 30 seconds until fragrant",
            "6": "Drain pasta and add to the garlic oil",
            "7": "Toss everything together and serve hot"
        }
    }
    
    # Option 2: Test with suggester integration
    # Uncomment the line below to test with real recipes from suggester
    # await test_with_suggester()
    
    # Run with the test recipe
    await run_sous_chef_session(test_recipe)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting.")
