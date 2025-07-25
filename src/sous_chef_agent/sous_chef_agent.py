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

# Shortened recipe steps for faster testing (top 4 steps)
recipe_steps = {
    1: "Preheat the oven to 400°F (200°C).",
    2: "In a baking dish, toss cherry tomatoes with olive oil.",
    3: "Place a block of feta in the center of the dish and drizzle it with more olive oil.",
    4: "Bake for 5 seconds, or until the tomatoes burst and the feta is soft and melty."
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
    """A stateful tool to manage the recipe's progress using session state."""
    def __init__(self, steps: dict):
        super().__init__(name="recipe_manager", description="Manages recipe steps")
        self._steps = steps
        self._step_keys = sorted(steps.keys())

    def get_current_step(self, tool_context: ToolContext) -> dict:
        """Gets the current step of the recipe from session state."""
        current_index = tool_context.state.get("step_index", 0)
        
        logger.info(f"  [Tool Call] get_current_step: Current step_index in state: {current_index}")

        if current_index >= len(self._step_keys):
            tool_context.state["recipe_completed"] = True
            return {"step": COMPLETION_PHRASE}

        current_step_key = self._step_keys[current_index]
        current_step_text = self._steps[current_step_key]

        # Store current step info in state
        tool_context.state["current_step_text"] = current_step_text
        tool_context.state["current_step_number"] = current_index + 1

        logger.info(f"  [Tool Call] get_current_step: Now on step {current_index + 1}: {current_step_text}")
        return {"step": current_step_text, "step_number": current_index + 1}

    def advance_step(self, tool_context: ToolContext) -> dict:
        """Advances the recipe to the next step in session state."""
        current_index = tool_context.state.get("step_index", 0)
        new_index = current_index + 1
        tool_context.state["step_index"] = new_index
        
        logger.info(f"  [Tool Call] advance_step: Advanced from step {current_index + 1} to step {new_index + 1}")
        return {"status": "success", "message": f"Advanced to step {new_index + 1}."}

def wait_for_user_confirmation(tool_context: ToolContext) -> dict:
    """Wait for user to type 'next' to continue."""
    logger.info(f"  [Tool Call] wait_for_user_confirmation triggered by {tool_context.agent_name}")
    return {"status": "waiting", "message": "Please type 'next' to continue to the next step."}

# Instantiate the tools
recipe_tool = RecipeManagerTool(recipe_steps)

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
    tools=[timer_tool, wait_for_user_confirmation],
    instruction=f"""You are an expert chef's assistant.
    Your current instruction is: {{current_step}}

    1. If the current step is '{COMPLETION_PHRASE}', do nothing and output that phrase.
    2. Otherwise, clearly and concisely state the instruction to the user.
    3. **Analyze the instruction for a time duration.** If you see a time like "30-35 minutes" or "10 seconds", you MUST call the `timer_tool`. Convert the time to seconds (e.g., 30 minutes = 1800 seconds). Use the lower number if there is a range.
    4. After stating the instruction (and setting a timer if needed), you MUST call the `wait_for_user_confirmation` tool to wait for the user.
    """
)

# Agent 3 (in loop): Checks if the recipe is finished to exit the loop
completion_checker_agent = Agent(
    name="CompletionCheckerAgent",
    model=MODEL,
    tools=[exit_loop],
    instruction=f"""You are the completion checker.
    Check the session state to see if the recipe is completed.
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
    max_iterations=len(recipe_steps) + 2  # Set a max iteration to avoid infinite loops
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
            Then immediately tell them to get ready because you're about to start with the first step.
            Keep it brief and enthusiastic. End by saying "Let's start cooking!"
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
# We don't need the run_agent_turn function anymore since we're using persistent runners

async def main():
    """Simulates a user interaction with the Sous Chef agent."""
    # Create session service and session with initial state
    session_service = InMemorySessionService()
    initial_state = {
        "step_index": 0,  # Start at step 0
        "recipe_completed": False
    }
    
    session = await session_service.create_session(
        app_name=APP_NAME, 
        user_id=USER_ID,
        state=initial_state
    )
    
    # Create a single runner instance that persists throughout the conversation
    runner = Runner(agent=sous_chef_agent, session_service=session_service, app_name=APP_NAME)
    step_advance_runner = Runner(agent=step_advancer_agent, session_service=session_service, app_name=APP_NAME)
    
    current_query_content = Content(parts=[Part(text="Hello, let's start cooking!")], role="user")
    
    while True:
        final_response_text = ""
        waiting_for_user = False
        
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session.id,
            new_message=current_query_content
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        logger.info(f"[ADK Event] Author: {event.author}, Text: {part.text}")
                        print(f"< Agent: {part.text}")
                        final_response_text += part.text
                    elif part.function_call:
                        logger.info(f"[ADK Event] Author: {event.author}, Function Call: {part.function_call.name}({part.function_call.args})")
                        # Check if this is a wait for user confirmation
                        if part.function_call.name == "wait_for_user_confirmation":
                            waiting_for_user = True
            else:
                logger.info(f"[ADK Event] Author: {event.author}, No content parts.")
            
            if event.is_final_response():
                logger.info(f"< Agent Final Response: {final_response_text}")
                if COMPLETION_PHRASE in final_response_text:
                    print("🎉 Recipe completed! Enjoy your meal!")
                    return
                break
        
        # Check current session state
        current_session = await session_service.get_session(
            app_name=APP_NAME,
            user_id=USER_ID, 
            session_id=session.id
        )
        logger.info(f"Current session state: {current_session.state}")
        
        # Get user input
        if waiting_for_user:
            user_input = input("\n(Type 'next' to continue, or 'quit' to exit): ")
        else:
            user_input = input("\n(Type your message or 'quit' to exit): ")
            
        if user_input.lower() == 'quit':
            break
            
        # If user typed 'next' after a confirmation request, advance the step
        if waiting_for_user and user_input.lower() == 'next':
            # First advance the step
            async for event in step_advance_runner.run_async(
                user_id=USER_ID,
                session_id=session.id,
                new_message=Content(parts=[Part(text="advance")], role="user")
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.function_call and part.function_call.name == "advance_step":
                            logger.info(f"Step advanced: {part.function_call}")
            
            # Then continue with the cooking loop
            current_query_content = Content(parts=[Part(text="next step")], role="user")
        else:
            # Regular user input
            current_query_content = Content(parts=[Part(text=user_input)], role="user")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting.")