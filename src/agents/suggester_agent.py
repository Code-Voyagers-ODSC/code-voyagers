# agents/suggester_agent.py

import json
import re
from typing import List
from dotenv import load_dotenv
from pyprojroot.here import here

from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

from tools.search_tool import web_search_recipes_tool

load_dotenv(here(".env"))  # loads GOOGLE_API_KEY, etc.

# Define the Agent, passing your search function directly
recipe_agent = LlmAgent(
    name="recipe_suggester",
    model="gemini-2.0-flash",
    instruction=(
        "You are a cooking assistant. From the search results, select the 3-4 best recipes that match the requested ingredients. "
        "Be flexible - if a recipe contains most of the ingredients or similar ingredients, include it.\n\n"
        "IMPORTANT:\n"
        "• Even if the search results don't perfectly match all ingredients, extract what you can.\n"
        "• For example, if searching for 'chicken pasta garlic' and you find 'garlic chicken' recipes, adapt them.\n\n"
        "Return ONLY a valid JSON array with no additional text or formatting.\n\n"
        "Each recipe must include the following structure:\n\n"
        "{\n"
        "  \"id\": \"recipe_1\",\n"
        "  \"summary\": {\n"
        "    \"title\": \"...\",\n"
        "    \"link\": \"...\",\n"
        "    \"description\": \"...\",\n"
        "    \"estimated_time\": \"...\",\n"
        "    \"difficulty\": \"...\",\n"
        "    \"cuisine_type\": \"...\",\n"
        "    \"serves\": \"...\",\n"
        "    \"food_safety_summary\": \"...\"\n"
        "  },\n"
        "  \"details\": {\n"
        "    \"ingredients\": [\"...\"],\n"
        "    \"equipment_needed\": [\"...\"],\n"
        "    \"prep_time\": \"...\",\n"
        "    \"cook_time\": \"...\",\n"
        "    \"method_overview\": \"...\",\n"
        "    \"key_techniques\": [\"...\"],\n"
        "    \"food_safety_details\": {\n"
        "      \"temperature_guidelines\": \"...\",\n"
        "      \"storage_instructions\": \"...\",\n"
        "      \"handling_tips\": \"...\"\n"
        "    },\n"
        "    \"dietary_info\": [\"...\"],\n"
        "    \"substitutions\": [\"...\"],\n"
        "    \"chef_tips\": [\"...\"],\n"
        "    \"serving_suggestions\": [\"...\"],\n"
        "    \"make_ahead_notes\": \"...\",\n"
        "    \"troubleshooting\": [\"...\"]\n"
        "  },\n"
        "  \"sous_chef_format\": {\n"
        "    \"name\": \"Recipe Title\",\n"
        "    \"steps\": {\n"
        "      \"1\": \"First step - be specific and clear\",\n"
        "      \"2\": \"Second step - include temperatures, times, and techniques\",\n"
        "      \"3\": \"Third step - mention any timers needed (e.g., 'Bake for 20 minutes')\",\n"
        "      \"4\": \"Continue with numbered steps until recipe is complete\"\n"
        "    }\n"
        "  }\n"
        "}\n\n"
        "IMPORTANT FOR SOUS_CHEF_FORMAT:\n"
        "• Break down the cooking method into clear, sequential numbered steps\n"
        "• Each step should be actionable and specific\n"
        "• Include timing information where relevant (e.g., 'Bake for 20 minutes', 'Simmer for 15 minutes')\n"
        "• Keep steps concise but complete\n"
        "• Number steps as strings (\"1\", \"2\", \"3\", etc.)\n"
        "• Make sure the steps flow logically from start to finish\n\n"
    ),
    description="Suggest cooking recipes based on input ingredients",
    tools=[web_search_recipes_tool]
)

async def smart_recipe_search_handler(ingredients: List[str]):
    # 1) Start an in‑memory session
    session_svc = InMemorySessionService()
    session = await session_svc.create_session(
        app_name="recipe_suggestor_app",
        user_id="anonymous",
        session_id=None  # let ADK generate one
    )

    # 2) Create a runner for that session
    runner = Runner(
        agent=recipe_agent,
        app_name="recipe_suggestor_app",
        session_service=session_svc
    )

    # 3) Send the user's ingredients as JSON
    payload = json.dumps({"ingredients": ingredients})
    user_msg = types.Content(role="user", parts=[types.Part(text=payload)])

    # 4) Run the agent (it will invoke web_search_recipes_tool under the hood)
    raw_response = None
    async for evt in runner.run_async(
        user_id="anonymous",
        session_id=session.id,           # ← use `session.id`, not `session.session_id`
        new_message=user_msg
    ):
        if evt.is_final_response():
            raw_response = evt.content.parts[0].text
            break

    if not raw_response:
        return {"error": "Agent produced no response."}

    # 5) Clean & parse the JSON array
    try:
        cleaned = clean_json_response(raw_response)
        recipes = json.loads(cleaned)
        return {"recipes": recipes}
    except Exception as e:
        return {
            "error": "Failed to parse agent response",
            "debug": str(e),
            "raw_preview": raw_response[:200]
        }

def clean_json_response(txt: str) -> str:
    # strip markdown fences
    txt = re.sub(r'```json\s*', '', txt)
    txt = re.sub(r'```', '', txt)
    # extract the array
    start = txt.find('[')
    end = txt.rfind(']')
    if start == -1 or end == -1:
        raise ValueError("No JSON array found")
    arr = txt[start:end+1]
    # remove trailing commas
    return re.sub(r',\s*([\]}])', r'\1', arr)

def extract_sous_chef_format(recipe_response):
    """
    Helper function to extract just the sous_chef_format from a recipe response.
    Use this when you want to pass a recipe to the sous chef agent.
    """
    if "recipes" in recipe_response:
        recipes = recipe_response["recipes"]
        if recipes and len(recipes) > 0:
            # Get the first recipe's sous_chef_format
            first_recipe = recipes[0]
            if "sous_chef_format" in first_recipe:
                return first_recipe["sous_chef_format"]
    return None

# Example usage:
# response = await smart_recipe_search_handler(["chicken", "pasta", "garlic"])
# sous_chef_recipe = extract_sous_chef_format(response)
# # Now you can use sous_chef_recipe directly with the sous chef agent