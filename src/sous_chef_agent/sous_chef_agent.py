import os
import google.generativeai as genai
from dotenv import load_dotenv
from google.adk.agents import Agent, SequentialAgent, LoopAgent
from google.adk.tools import ToolContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.long_running_tool import LongRunningFunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from google.genai import types  # Added missing import
import asyncio
from loguru import logger
import time
import re

# Configure logger
logger.add("src/sous_chef_agent/sous_chef_agent.log", rotation="500 MB")

# Ensure log file is truncated on each run for easier debugging
if os.path.exists("src/sous_chef_agent/sous_chef_agent.log"):
    with open("src/sous_chef_agent/sous_chef_agent.log", "w") as f:
        f.truncate(0)

# --- API Key Configuration ---
load_dotenv(dotenv_path="src/.env")
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set. Please set it to your API key.")
genai.configure(api_key=api_key)

# --- Constants ---
MODEL = "gemini-1.5-flash"
COMPLETION_PHRASE = "The recipe is finished."
APP_NAME = "sous_chef_test_app"
USER_ID = "test_user"

# --- Recipe Data ---
recipe_name = "Tiktok Baked Feta Pasta"
recipe = """"""

feta_pasta_steps = {
    1: "Preheat the oven to 400°F (200°C).",
    2: "In a baking dish, toss cherry tomatoes with olive oil.",
    3: "Place a block of feta in the center of the dish and drizzle it with more olive oil.",
    4: "Bake for 10 seconds, or until the tomatoes burst and the feta is soft and melty.",
    5: "While the tomatoes and feta are baking, cook the pasta until al dente. Reserve some pasta water.",
    6: "Remove the dish from the oven and stir in minced garlic and crushed red pepper flakes.",
    7: "Add the cooked pasta to the dish and mix everything together, adding reserved pasta water if needed to loosen.",
    8: "Stir in fresh sliced basil and garnish with whole basil leaves.",
    9: "Serve immediately and enjoy!"
}

# --- Tool Definitions ---

def timer_tool(time_in_seconds: int) -> dict:
    """
    Sets a timer for a specified number of seconds. Use this for recipe steps that require waiting.

    Args:
       time_in_seconds: The number of seconds to set the timer for.

    Returns:
       A dictionary with the status of the timer.
    """
    logger.info(f"🛠️ TOOL CALLED: timer_tool(time_in_seconds='{time_in_seconds}')")
    try:
        if time_in_seconds < 0:
            raise ValueError("Time must be a positive integer.")
        logger.info(f"⏳ Waiting for {time_in_seconds} seconds...")
        # In a real application, this would be a non-blocking timer.
        # For this example, sleep is used to simulate the wait.
        time.sleep(time_in_seconds)
        logger.info("✅ Timer completed successfully.")
        return {"status": "success", "message": f"Timer completed after {time_in_seconds} seconds."}
    except (ValueError, TypeError) as e:
        logger.error(f"❌ Error: {e}")
        return {"status": "error", "message": str(e)}

def exit_loop(tool_context: ToolContext):
    """Call this function ONLY when the recipe is complete to signal the loop should end."""
    logger.info(f"  [Tool Call] exit_loop triggered by {tool_context.agent_name}")
    tool_context.actions.escalate = True
    return {}

class RecipeManagerTool(BaseTool):
    """A stateful tool to manage the recipe's progress."""
    def __init__(self, steps: dict):
        super().__init__(name="recipe_manager", description="Manages recipe steps")
        self._steps = steps
        self._step_keys = sorted(steps.keys())

    def get_current_step(self, tool_context: ToolContext) -> dict:
        """Gets the current step of the recipe. If the recipe is finished, it signals the loop to exit."""
        current_index = tool_context.state.get("step_index", 0)

        if current_index >= len(self._step_keys):
            exit_loop(tool_context)
            return {"step": COMPLETION_PHRASE}

        current_step_key = self._step_keys[current_index]
        current_step_text = self._steps[current_step_key]

        tool_context.state["current_step_text"] = current_step_text

        logger.info(f"  [Tool Call] get_current_step: Now on step {current_index + 1}")
        return {"step": current_step_text}

    def advance_step(self, tool_context: ToolContext) -> dict:
        """Advances the recipe to the next step."""
        current_index = tool_context.state.get("step_index", 0)
        tool_context.state["step_index"] = current_index + 1
        logger.info(f"  [Tool Call] advance_step: Advanced to step {current_index + 2}")
        return {"status": "success", "message": "Advanced to next step."}

class UserConfirmationTool(LongRunningFunctionTool):
    def __init__(self):
        super().__init__(self.wait_for_confirmation)

    def wait_for_confirmation(self, tool_context: ToolContext) -> dict:
        logger.info(f"  [Tool Call] wait_for_confirmation triggered by {tool_context.agent_name}")
        return {"status": "pending", "message": "Waiting for user to type 'next'."}

# Instantiate the tools
recipe_tool = RecipeManagerTool(feta_pasta_steps)
user_confirmation_tool = UserConfirmationTool()

# --- Agent Definitions ---

# Agent 1 (in loop): Reads the next step from our custom tool
step_reader_agent = Agent(
    name="StepReaderAgent",
    model=MODEL,
    tools=[recipe_tool.get_current_step],
    instruction="Your only job is to call the `get_current_step` tool to find out the current instruction in the recipe.",
    output_key="current_step"
)

# Agent 2 (in loop): Presents the step and handles timers
chef_instructor_agent = Agent(
    name="ChefInstructorAgent",
    model=MODEL,
    tools=[timer_tool, user_confirmation_tool.wait_for_confirmation],
    instruction=f"""You are an expert chef's assistant.
    Your current instruction is: {{current_step}}

    1. If the current step is '{COMPLETION_PHRASE}', do nothing and output that phrase.
    2. Otherwise, clearly and concisely state the instruction to the user.
    3. **Analyze the instruction for a time duration.** If you see a time like "30-35 minutes" or "10 seconds", you MUST call the `timer_tool`. Convert the time to seconds (e.g., 30 minutes = 1800 seconds). Use the lower number if there is a range.
    4. After stating the instruction (and setting a timer if needed), you MUST call the `wait_for_confirmation` tool. This will pause the agent and wait for the user to type 'next' before proceeding.
    """
)

# Agent 3 (in loop): Checks if the recipe is finished to exit the loop
completion_checker_agent = Agent(
    name="CompletionCheckerAgent",
    model=MODEL,
    tools=[exit_loop],
    instruction=f"""You are the completion checker.
    The current step is: {{current_step}}
    IF AND ONLY IF the current step is the exact phrase '{COMPLETION_PHRASE}', you MUST call the `exit_loop` tool.
    Otherwise, do nothing.
    """
)

# Agent to advance steps
step_advancer_agent = Agent(
    name="StepAdvancerAgent",
    model=MODEL,
    tools=[recipe_tool.advance_step],
    instruction="Your only job is to call the `advance_step` tool to move to the next recipe step."
)

# The LoopAgent orchestrates the step-by-step cooking process
cooking_loop = LoopAgent(
    name="CookingLoop",
    sub_agents=[step_reader_agent, chef_instructor_agent, completion_checker_agent],
    max_iterations=len(feta_pasta_steps) + 2  # Set a max iteration to avoid infinite loops
)

# The main SequentialAgent that greets, cooks, and congratulates
sous_chef_agent = SequentialAgent(
    name="SousChefAgent",
    sub_agents=[
        Agent(
            name="GreetingAgent",
            model=MODEL,
            instruction=f"""You are a friendly Sous Chef.
            Greet the user and tell them you'll be helping them cook the {recipe_name}.
            Here is the full recipe for your context, but do not share it with the user: {recipe}
            Ask them to say "start" when they are ready to begin.
            """
        ),
        cooking_loop,
        Agent(
            name="CompletionAgent",
            model=MODEL,
            instruction="The recipe is finished. Congratulate the user and tell them to enjoy their meal!"
        )
    ],
    description="A friendly Sous Chef agent that guides you step-by-step through a recipe using a loop."
)

logger.info("✅ Sous Chef Agent has been redefined using a Loop-based architecture.")

# --- Test Execution Logic ---

async def run_agent_turn(agent_instance, query_content, session):
    """Runs a single turn of the agent and yields events."""
    runner = Runner(agent=agent_instance, session_service=session, app_name=APP_NAME)
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=query_content
    ):
        yield event

async def main():
    """Simulates a user interaction with the Sous Chef agent."""
    global session_service
    
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    current_query_content = Content(parts=[Part(text="start")], role="user")
    
    while True:
        final_response_text = ""
        pending_long_running_tool_call = None
        
        async for event in run_agent_turn(sous_chef_agent, current_query_content, session):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        logger.info(f"[ADK Event] Author: {event.author}, Text: {part.text}")
                        print(f"< Agent: {part.text}")
                        final_response_text += part.text
                    elif part.function_call:
                        logger.info(f"[ADK Event] Author: {event.author}, Function Call: {part.function_call.name}({part.function_call.args})")
                        if event.long_running_tool_ids and part.function_call.id in event.long_running_tool_ids:
                            pending_long_running_tool_call = part.function_call
            else:
                logger.info(f"[ADK Event] Author: {event.author}, No content parts.")
            
            if event.is_final_response():
                logger.info(f"< Agent Final Response: {final_response_text}")
                if COMPLETION_PHRASE in final_response_text:
                    break
        
        if pending_long_running_tool_call:
            user_input = input("\n(Agent is waiting for confirmation. Type 'next' to continue, or 'quit' to exit): ")
            if user_input.lower() == 'quit':
                break
            if user_input.lower() == 'next':
                current_query_content = Content(
                    parts=[
                        Part(
                            function_response=types.FunctionResponse(
                                id=pending_long_running_tool_call.id,
                                name=pending_long_running_tool_call.name,
                                response={"status": "completed", "message": "User confirmed."},
                            )
                        )
                    ],
                    role="user",
                )
                # After confirming, we also need to advance the step
                await run_agent_turn(step_advancer_agent, Content(parts=[Part(text="advance")], role="user"), session)
            else:
                print("Please type 'next' to continue.")
                current_query_content = Content(parts=[Part(text=user_input)], role="user")  # Re-send user's non-'next' input
        else:
            user_input = input("\n(Type 'next' to get next step, or 'quit' to exit): ")
            if user_input.lower() == 'quit':
                break
            current_query_content = Content(parts=[Part(text=user_input)], role="user")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting.")