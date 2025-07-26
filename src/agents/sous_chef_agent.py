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

# Add project root to path for imports
project_root = here()
sys.path.insert(0, str(project_root))

from tools.timer_tool import parse_timer_duration, timer_tool, set_custom_timer

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

MODEL = "gemini-1.5-flash"
COMPLETION_PHRASE = "The recipe is finished."
APP_NAME = "sous_chef_test_app"
USER_ID = "test_user"

recipe = {
    "name": "Tiktok Baked Feta Pasta",
    "steps": {
        1: "Preheat the oven to 400°F (200°C).",
        2: "In a baking dish, toss cherry tomatoes with olive oil.",
        3: "Place a block of feta in the center of the dish and drizzle it with more olive oil.",
        4: "Put the dish in the oven. When ready to time the baking, say 'next' again to start a 20-second timer.",
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


recipe_tool = RecipeManagerTool(recipe["steps"])

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
    instruction=f"""You are a friendly Sous Chef helping users cook {recipe["name"]} step by step.

WORKFLOW:
1. First interaction: Greet, get_current_step, present step, wait_for_user_confirmation
2. User says 'next': advance_step, get_current_step, present step, handle timers if needed
3. Timer workflow: parse_timer_duration → offer timer → user "start" → timer_tool
4. Completion: If get_current_step returns completion phrase, call exit_loop

TIMER RULES:
- Use parse_timer_duration to extract duration
- Say: "I'll start a [duration] timer when ready. Type 'start' to begin."
- User "start": Call timer_tool immediately
- Custom duration: Call set_custom_timer, wait for "start"

Keep responses concise and helpful.""",
)


async def main():
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        state={"step_index": 0, "recipe_completed": False},
    )

    runner = Runner(
        agent=sous_chef_agent, session_service=session_service, app_name=APP_NAME
    )
    current_query_content = Content(
        parts=[Part(text="Hello, let's start cooking!")], role="user"
    )

    iteration_count = 0
    max_iterations = 20

    while iteration_count < max_iterations:
        iteration_count += 1
        final_response_text = ""
        waiting_for_user = False
        timer_called = False
        timer_duration = 0

        async for event in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=current_query_content
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
                                timer_duration = part.function_call.args[
                                    "time_in_seconds"
                                ]

            if event.is_final_response():
                print(f"\n🍴 Sous Chef: {final_response_text}")

                if timer_called and timer_duration > 0:
                    run_countdown_timer(timer_duration)
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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting.")
