import warnings
import logging
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
from google.genai import types
import asyncio
from loguru import logger
import time
import re

# Suppress all warnings related to function calls and non-text parts
warnings.filterwarnings("ignore")
logging.getLogger("google").setLevel(logging.ERROR)
logging.getLogger("google.adk").setLevel(logging.ERROR)
logging.getLogger("google.generativeai").setLevel(logging.ERROR)

# Configure logger to separate CLI output from file logging
logger.remove()  # Remove the default handler that outputs to stderr
logger.add("src/sous_chef_agent/sous_chef_agent.log", rotation="500 MB", level="DEBUG")  # File logging only

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
        
        logger.info(f"⏳ Timer tool called for {time_in_seconds} seconds")
        
        # Return immediately - the timer message will be shown by the agent
        return {"status": "timer_ready", "duration": time_in_seconds, "message": f"Timer set for {time_in_seconds} seconds"}
        
    except (ValueError, TypeError) as e:
        logger.error(f"❌ Error: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"❌ Unexpected error in timer: {e}")
        return {"status": "error", "message": f"Timer error: {str(e)}"}

def run_countdown_timer(time_in_seconds: int) -> dict:
    """
    Actually runs the countdown timer. This will be called separately after the agent announces it.
    """
    logger.info(f"🛠️ COUNTDOWN STARTED: {time_in_seconds} seconds")
    try:
        print(f"⏰ Starting {time_in_seconds} second timer...")
        
        # Countdown with logging
        for remaining in range(time_in_seconds, 0, -1):
            logger.info(f"⏰ Timer: {remaining} seconds remaining...")
            print(f"⏰ {remaining}...")
            time.sleep(1)
        
        logger.info("🔔 Timer completed! Time's up!")
        print("🔔 Timer completed! Time's up!")
        
        return {"status": "success", "message": f"Timer completed after {time_in_seconds} seconds."}
    except Exception as e:
        logger.error(f"❌ Unexpected error in countdown: {e}")
        return {"status": "error", "message": f"Countdown error: {str(e)}"}

def exit_loop(tool_context: ToolContext):
    """Call this function ONLY when the recipe is complete to signal the loop should end."""
    logger.info(f"  [Tool Call] exit_loop triggered by {tool_context.agent_name}")
    tool_context.state["recipe_completed"] = True  # Set completion flag
    tool_context.actions.escalate = True
    return {"status": "success", "message": "Recipe completed, exiting loop."}

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
            return {"step": COMPLETION_PHRASE, "step_number": "complete", "is_complete": True}

        current_step_key = self._step_keys[current_index]
        current_step_text = self._steps[current_step_key]

        # Store current step info in state
        tool_context.state["current_step_text"] = current_step_text
        tool_context.state["current_step_number"] = current_index + 1

        logger.info(f"  [Tool Call] get_current_step: Now on step {current_index + 1}: {current_step_text}")
        return {
            "step": current_step_text, 
            "step_number": current_index + 1,
            "is_complete": False
        }

    def advance_step(self, tool_context: ToolContext) -> dict:
        """Advances the recipe to the next step in session state."""
        current_index = tool_context.state.get("step_index", 0)
        new_index = current_index + 1
        tool_context.state["step_index"] = new_index
        
        logger.info(f"  [Tool Call] advance_step: Advanced from step {current_index + 1} to step {new_index + 1}")
        
        # Check if we've completed all steps
        if new_index >= len(self._step_keys):
            tool_context.state["recipe_completed"] = True
            logger.info(f"  [Tool Call] advance_step: Recipe completed!")
            
        return {"status": "success", "message": f"Advanced to step {new_index + 1}."}

def wait_for_user_confirmation(tool_context: ToolContext) -> dict:
    """Wait for user to type 'next' to continue."""
    logger.info(f"  [Tool Call] wait_for_user_confirmation triggered by {tool_context.agent_name}")
    return {"status": "waiting", "message": "Please type 'next' to continue to the next step."}

# Instantiate the tools
recipe_tool = RecipeManagerTool(recipe_steps)

# --- Simple Agent with All Tools (like version that was working) ---
sous_chef_agent = Agent(
    name="SousChefAgent",
    model=MODEL,
    tools=[
        recipe_tool.get_current_step, 
        recipe_tool.advance_step, 
        timer_tool, 
        wait_for_user_confirmation, 
        exit_loop
    ],
    instruction=f"""You are a friendly Sous Chef helping users cook {recipe_name} step by step.

IMPORTANT: Always provide text responses explaining what you're doing, even when calling functions!

WORKFLOW:
1. **First interaction (when user says hello)**: 
   - Greet the user warmly and explain you'll guide them through the recipe
   - Call get_current_step to see the first step
   - Present the step clearly and enthusiastically 
   - Call wait_for_user_confirmation and STOP

2. **When user says 'next' or similar**:
   - Call advance_step to move to the next step
   - Call get_current_step to see the new step
   - Present the new step clearly and enthusiastically
   - Call wait_for_user_confirmation and STOP

3. **Timer steps special handling**:
   When a step mentions time, look for these EXACT patterns:
   - "5 seconds" → call timer_tool(5)
   - "20 minutes" → call timer_tool(1200) 
   - "1 hour" → call timer_tool(3600)
   
   IMPORTANT: If you see "Bake for 5 seconds", that means 5 seconds, NOT 400 or any other number!
   
   Process: Present the step but explain the timer will start when they're ready
   Wait for user to say 'next' to actually start the timer
   When they say 'next': First say you're starting the timer, then call timer_tool, then wait for confirmation again

4. **When recipe is complete**:
   - If get_current_step returns "The recipe is finished", call exit_loop
   - Congratulate the user!

TIMER HANDLING EXAMPLE:
First response: "Step 4: Bake for 5 seconds! Get everything in the oven first, then type 'next' when you're ready for me to start the 5-second timer!"
User says 'next': "Perfect! Starting the 5-second timer now!" [call timer_tool(5)] "Timer will count down, then we'll continue!"

CRITICAL: Always use the EXACT time mentioned in the recipe step! "5 seconds" = timer_tool(5), not 400!

Remember: ALWAYS provide enthusiastic text responses, and let users confirm before starting timers!"""
)

logger.info("✅ Sous Chef Agent has been redefined as a simple agent with all tools.")

# --- Test Execution Logic ---

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
    
    # Create a single runner instance that handles everything
    runner = Runner(agent=sous_chef_agent, session_service=session_service, app_name=APP_NAME)
    
    current_query_content = Content(parts=[Part(text="Hello, let's start cooking!")], role="user")
    
    iteration_count = 0
    max_iterations = 20  # Prevent infinite loops
    
    while iteration_count < max_iterations:
        iteration_count += 1
        final_response_text = ""
        waiting_for_user = False
        timer_called = False
        timer_duration = 0
        
        logger.info(f"=== ITERATION {iteration_count} ===")
        
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session.id,
            new_message=current_query_content
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        logger.info(f"[ADK Event] Author: {event.author}, Text: {part.text}")
                        final_response_text += part.text
                    elif part.function_call:
                        logger.info(f"[ADK Event] Author: {event.author}, Function Call: {part.function_call.name}({part.function_call.args})")
                        
                        # Check if this is a wait for user confirmation
                        if part.function_call.name == "wait_for_user_confirmation":
                            waiting_for_user = True
                        elif part.function_call.name == "timer_tool":
                            timer_called = True
                            # Extract timer duration from function call
                            if 'time_in_seconds' in part.function_call.args:
                                timer_duration = part.function_call.args['time_in_seconds']
            else:
                logger.info(f"[ADK Event] Author: {event.author}, No content parts.")
            
            if event.is_final_response():
                logger.info(f"< Agent Final Response: {final_response_text}")
                
                # Clean console output - show the complete response
                print(f"\n🍴 Sous Chef: {final_response_text}")
                
                # If a timer was called, run the countdown AFTER the agent's response
                if timer_called and timer_duration > 0:
                    print(f"\n⏳ Now starting the {timer_duration}-second timer...")
                    run_countdown_timer(timer_duration)
                    print(f"🔔 Timer finished! Continuing with the recipe...\n")
                
                # Check if recipe is completed
                if COMPLETION_PHRASE in final_response_text or "Congratulations" in final_response_text or "recipe is complete" in final_response_text.lower():
                    print("🎉 Recipe completed! Enjoy your meal!")
                    return
                break
        
        # Check current session state after each interaction (for debugging only)
        current_session = await session_service.get_session(
            app_name=APP_NAME,
            user_id=USER_ID, 
            session_id=session.id
        )
        logger.info(f"Current session state: {current_session.state}")
        # Note: Session state is logged but not shown to user
        
        # Get user input
        if waiting_for_user:
            user_input = input("\n⏭️  Type 'next' to continue (or 'quit' to exit): ")
        else:
            user_input = input("\n💬 Type your message (or 'quit' to exit): ")
            
        if user_input.lower() == 'quit':
            break
            
        # Continue with user input
        current_query_content = Content(parts=[Part(text=user_input)], role="user")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting.")