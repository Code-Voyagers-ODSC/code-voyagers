from google.adk.agents import Agent
from google.adk.tools import google_search  # Import the tool

food = "remen"
promnt = "give only" + food + "resipes"

root_agent = Agent(
   # A unique name for the agent.
   name="basic_search_agent",
   # The Large Language Model (LLM) that agent will use.
   # Please fill in the latest model id that supports live from
   # https://google.github.io/adk-docs/get-started/streaming/quickstart-streaming/#supported-models
   model="gemini-live-2.5-flash-preview",  # for example: model="gemini-2.0-flash-live-001" or model="gemini-2.0-flash-live-preview-04-09"
   # A short description of the agent's purpose.
   #description="Agent to answer questions using Google Search.",
   description="Agent to give out cookie resips",

   # instruction="You are an expert researcher. Only give short, factual answers — 2-3 sentences max.",
   instruction="give only cookie resipes",
   # Add google_search tool to perform grounding with Google search.
   tools=[google_search]
   )