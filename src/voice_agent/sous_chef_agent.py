from google.adk.agents import Agent, SequentialAgent, LoopAgent, ParallelAgent
from google.adk.tools import google_search  # Import the tool
from google.adk.memory import InMemoryMemoryService
from google.adk.tools import load_memory # Tool to query memory
from google.adk.tools import google_search, ToolContext
from google.adk.core import Tool, ToolContext # Tool to keep track of steps

from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService, Session
from google.adk.memory import InMemoryMemoryService # Import MemoryService
from google.adk.runners import Runner
from google.adk.tools import load_memory # Tool to query memory
from google.genai.types import Content, Part

from google.adk.agents import Agent
from google.adk.tools import google_search  # Import the tool

import time
import asyncio
from IPython.display import display, Markdown

recipe = """
Tiktok Baked Feta Pasta
Baked feta pasta has it all, big bold flavors, creamy comfort, and carbs!

Baked feta pasta is the perfect summer food: it’s creamy, bright and tomato-y, and SO damn delicious. It’s probably the simplest pasta dish you’ll make this month and the reward is so high for an incredibly low effort.

tiktok pasta | www.iamafoodblog.com
What is tiktok pasta?

It’s super simple: cherry tomatoes are tossed with olive oil and placed in a baking dish with a block of feta. Everything gets baked up until the tomatoes burst, releasing their sweet and jammy flavors. The feta gets melty and oozy. You mix it all up into a quick sauce, toss in minced garlic, basil, crushed red pepper, and pasta. Boom, dinner is done!

baked feta pasta | www.iamafoodblog.com
Tiktok pasta is so good and easy

Sometimes the best kind of cooking is the kind that takes no time at all so you can spend more time with loved ones enjoying the food. I love that the prep time for this dish is so low and the actual hands on time is super low. If you can stir, you can make this dish.

The dominant flavors of this pasta are feta and tomatoes, it’s practically a two ingredient pasta. If you’re not a huge feta fan, you can definitely use another cheese – baked brie, cream cheese, or ricotta would be amazing.

tiktok pasta | www.iamafoodblog.com
How to make tiktok pasta

    Toss: In a baking dish, toss cherry tomatoes with olive oil. Place a block of feta in the middle and drizzle some oil on top.
    Bake: Bake the tomatoes and feta in the oven until the tomatoes burst and the cheese is melty.
    Cook: While the feta is in the oven, cook the pasta.
    Stir: When the tomatoes and feta are done, stir in some minced garlic, some crushed red pepper flakes, and the pasta, loosening with some pasta water if needed. Finish with fresh basil.
    Eat: That’s it! Scoop it up an enjoy a bowl of pure cheesy carby comfort.

3 ingredient baked feta pasta | www.iamafoodblog.com
Tiktok pasta ingredients

    cherry tomatoes – the sweeter the better! There are so many types of mini tomatoes these days, from strawberry to grape to on the vine to heirloom. I used one package of classic cherry tomatoes and one package of cherry tomatoes on the vine.
    feta – you’ll want to get a nice higher quality Greek feta since it’s the main flavor of the dish. Grab a block of feta, the kind that comes in a brine, not the crumbles. If you want a milder, creamier feta, try French feta, it’s less tart than Greek.
    olive oil – most of the recipes I’ve seen call from anywhere from 1/4 to 1/2 cup of olive oil. I went with 1/3 cup, you want enough to coat the tomatoes and feta while having a bit of oil pool at the bottom of your baking dish so the tomatoes are essentially doing a tomato confit type thing. Too little olive oil and your tomatoes will end up drying out.
    pasta – you can use any shape you like, we went with casarecce the first time and rotini the second time and both were great.
    garlic – a couple cloves of minced garlic are mixed in and the residual heat of the tomatoes mellows the sharpness out while still giving you a huge hit of garlicky goodness.
    basil – fresh basil and tomatoes are perfect pairing. Slice some up to stir in and keep some extra leaves whole to garnish with!
"""

feta_pasta_steps = {
    1: "Preheat the oven to 400°F (200°C).",
    2: "In a baking dish, toss cherry tomatoes with olive oil.",
    3: "Place a block of feta in the center of the dish and drizzle it with more olive oil.",
    4: "Bake for 30–35 minutes, or until the tomatoes burst and the feta is soft and melty.",
    5: "While the tomatoes and feta are baking, cook the pasta until al dente. Reserve some pasta water.",
    6: "Remove the dish from the oven and stir in minced garlic and crushed red pepper flakes.",
    7: "Add the cooked pasta to the dish and mix everything together, adding reserved pasta water if needed to loosen.",
    8: "Stir in fresh sliced basil and garnish with whole basil leaves.",
    9: "Serve immediately and enjoy!"
}

current_step = feta_pasta_steps[2]

# --- Constants ---
APP_NAME = "sous_chef_example_app"
USER_ID = "mem_user"
MODEL = "gemini-live-2.5-flash-preview" # Use a valid model

# MOCK TIMER TOOL
def timer_tool(time: int) -> dict:
   """
   Sets a timer for a specified number of seconds.

   Args:
      time: The number of seconds to set the timer for.

   Returns:
      A dictionary with the status of the timer.
   """
   print(f"🛠️ TOOL CALLED: timer_tool(time='{time}')")

   # Sleep for the specified time to simulate a timer
   try:
      if time < 0:
         raise ValueError("Time must be a positive integer.")
      print(f"⏳ Waiting for {time} seconds...")
      time.sleep(time)
      print("✅ Timer completed successfully.")
      return {"status": "success", "message": f"Timer completed after {time} seconds."}
   except ValueError as e:
      print(f"❌ Error: {e}")
      return {"status": "error", "message": str(e)}
      
async def run_agent_query(agent: Agent, query: str, session: Session, user_id: str, is_router: bool = False):
    """Initializes a runner and executes a query for a given agent and session."""
    print(f"\n🚀 Running query for agent: '{agent.name}' in session: '{session.id}'...")

    runner = Runner(
        agent=agent,
        session_service=session_service,
        app_name=agent.name
    )

    final_response = ""
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=Content(parts=[Part(text=query)], role="user")
        ):
            if not is_router:
                # Let's see what the agent is thinking!
                print(f"EVENT: {event}")
            if event.is_final_response():
                final_response = event.content.parts[0].text
    except Exception as e:
        final_response = f"An error occurred: {e}"

    if not is_router:
     print("\n" + "-"*50)
     print("✅ Final Response:")
     display(Markdown(final_response))
     print("-"*50 + "\n")

    return final_response


# --- Agent Definitions ---
# Agent 2: Agent that can use memory
memory_recall_agent = LlmAgent(
    model=MODEL,
    name="MemoryRecallAgent",
    instruction="Use the 'load_memory' tool to get the current step of the recipe.",
    tools=[load_memory], # Give the agent the tool
    output_key="current_step"
)

timer_start_agent = LlmAgent(
    model=MODEL,
    name="TimerStartAgent",
    instruction="Use the 'timer_tool' to start a timer for the current step.",
    tools=[timer_tool], # Give the agent the tool
    output_key="current_step"
)

# Agent 1: Sous Chef Agent to provide step-by-step cooking instructions
sous_chef_agent = SequentialAgent(
   # A unique name for the agent.
   name="SousChefAgent",
   # The Large Language Model (LLM) that agent will use.
   # Please fill in the latest model id that supports live from
   # https://google.github.io/adk-docs/get-started/streaming/quickstart-streaming/#supported-models
   # model=MODEL,  # for example: model="gemini-2.0-flash-live-001" or model="gemini-2.0-flash-live-preview-04-09"
   sub_agents=[memory_recall_agent, transportation_agent],
   # A short description of the agent's purpose.
   description="Agent to give step by step steps to cook the given recipe.",
   # Instructions to set the agent's behavior.
   instruction="""
      You are an expert chef's assistant. 
      You concisely provide step-by-step instructions to cook the given recipe. 
      Here is the full recipe: {recipe}. 
      The current step you are on is {current_step}. 
      """,
   # Add google_search tool to perform grounding with Google search.
   tools=[load_memory],
   output_key="current_step"
)



# --- Services and Runner ---
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService() # Use in-memory for demo

runner = Runner(
    # Start with the info capture agent
    agent=info_capture_agent,
    app_name=APP_NAME,
    session_service=session_service,
    memory_service=memory_service # Provide the memory service to the Runner
)

# --- Agent Definitions for an Iterative Workflow ---

# A tool to signal that the loop should terminate
COMPLETION_PHRASE = "The recipe is finished."
def exit_loop(tool_context: ToolContext):
  """Call this function ONLY when the plan is approved, signaling the loop should end."""
  print(f"  [Tool Call] exit_loop triggered by {tool_context.agent_name}")
  tool_context.actions.escalate = True
  return {}

# Agent 1: Proposes an initial plan
planner_agent = Agent(
    name="planner_agent", model="gemini-2.5-flash", tools=[google_search],
    instruction="You are a trip planner. Based on the user's request, propose a single activity and a single restaurant. Output only the names, like: 'Activity: Exploratorium, Restaurant: La Mar'.",
    output_key="current_plan"
)

# Agent 2 (in loop): Critiques the plan
critic_agent = Agent(
    name="critic_agent", model="gemini-2.5-flash", tools=[google_search],
    instruction=f"""You are a logistics expert. Your job is to critique a travel plan. The user has a strict constraint: total travel time must be short.
    Current Plan: {{current_plan}}
    Use your tools to check the travel time between the two locations.
    IF the travel time is over 45 minutes, provide a critique, like: 'This plan is inefficient. Find a restaurant closer to the activity.'
    ELSE, respond with the exact phrase: '{COMPLETION_PHRASE}'""",
    output_key="criticism"
)

# Agent 3 (in loop): Refines the plan or exits
refiner_agent = Agent(
    name="refiner_agent", model="gemini-2.5-flash", tools=[exit_loop],
    instruction=f"""You are a trip planner, refining a plan based on criticism.
    Original Request: {{session.query}}
    Critique: {{criticism}}
    IF the critique is '{COMPLETION_PHRASE}', you MUST call the 'exit_loop' tool.
    ELSE, generate a NEW plan that addresses the critique. Output only the new plan names, like: 'Activity: de Young Museum, Restaurant: Nopa'.""",
    output_key="current_plan"
)

# ✨ The LoopAgent orchestrates the critique-refine cycle ✨
refinement_loop = LoopAgent(
    name="refinement_loop",
    sub_agents=[critic_agent, refiner_agent],
    max_iterations=3
)

# ✨ The SequentialAgent puts it all together ✨
iterative_planner_agent = SequentialAgent(
    name="iterative_planner_agent",
    sub_agents=[planner_agent, refinement_loop],
    description="A workflow that iteratively plans and refines a trip to meet constraints."
)

# recipe_steps = []

# Make a tool to track steps and end loop
class StepLoaderTool(Tool):
    def __init__(self, recipe_steps: dict):
        self.recipe_steps = list(recipe_steps.values())  # Convert dict to list
        self.step_index = 0
        self.name = "step_loader_tool"
    
    # def next_step(self, recipe_steps):
    #     if self.step_index >= len(self.recipe_steps):
    #       tool_context.actions.escalate = True  # End loop
    #       return {"current_step": "The recipe is finished."}
    #     step = self.recipe_steps[self.step_index]
    #     self.step_index += 1
    #     return {"current_step": step}
    
    def __call__(self, tool_context: ToolContext) -> dict:
        if self.step_index >= len(self.recipe_steps):
            tool_context.actions.escalate = True
            return {"current_step": "The recipe is finished."}
        
        step = self.recipe_steps[self.step_index]
        self.step_index += 1
        return {"current_step": step}

print("🤖 Agent team updated with an iterative LoopAgent workflow!")


# --- Scenario ---

# Turn 1: Capture some information in a session
print("--- Turn 1: Capturing Information ---")
session1_id = "session_info"
session1 = await runner.session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session1_id)
user_input1 = Content(parts=[Part(text="My favorite project is Project Alpha.")], role="user")

# Run the agent
final_response_text = "(No final response)"
async for event in runner.run_async(user_id=USER_ID, session_id=session1_id, new_message=user_input1):
    if event.is_final_response() and event.content and event.content.parts:
        final_response_text = event.content.parts[0].text
print(f"Agent 1 Response: {final_response_text}")

# Get the completed session
completed_session1 = await runner.session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=session1_id)

# Add this session's content to the Memory Service
print("\n--- Adding Session 1 to Memory ---")
memory_service = await memory_service.add_session_to_memory(completed_session1)
print("Session added to memory.")


root_agent = Agent(
   # A unique name for the agent.
   name="basic_search_agent",
   # The Large Language Model (LLM) that agent will use.
   model="gemini-live-2.5-flash-preview",  # for example: model="gemini-2.0-flash-live-001" or model="gemini-2.0-flash-live-preview-04-09"
   # A short description of the agent's purpose.
   description="Agent to answer questions using Google Search.",
   # Instructions to set the agent's behavior.
   instruction="You are an expert researcher. You always stick to the facts.",
   # Add google_search tool to perform grounding with Google search.
   tools=[google_search]
)