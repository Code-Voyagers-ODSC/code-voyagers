# src/backend/agents/suggester_agent.py

import json
import sys
import re
from typing import List, Dict
from dotenv import load_dotenv
from pyprojroot.here import here

# Add project root to Python path using pyprojroot
project_root = here()
sys.path.insert(0, str(project_root))

from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

from tools.search_tool import web_search_recipes_tool

load_dotenv(here(".env"))

# Define the Agent
recipe_agent = LlmAgent(
    name="recipe_suggester",
    model="gemini-2.0-flash",
    instruction=(
        "You are a cooking assistant. From the search results, select the 3-4 best recipes that match the requested ingredients. "
        "Be flexible - if a recipe contains most of the ingredients or similar ingredients, include it.\n\n"
        "IMPORTANT:\n"
        "• Even if the search results don't perfectly match all ingredients, extract what you can.\n"
        "• For example, if searching for 'chicken pasta garlic' and you find 'garlic chicken' recipes, adapt them.\n"
        "• Fill out all fields with relevant information from the search results.\n"
        "• If specific information isn't available, provide reasonable estimates or defaults.\n\n"
        "Return ONLY a valid JSON array with no additional text or formatting. Each recipe must follow this EXACT structure:\n\n"
        "[\n"
        "  {\n"
        "    \"id\": \"recipe_1\",\n"
        "    \"summary\": {\n"
        "      \"title\": \"Recipe Title\",\n"
        "      \"link\": \"URL to recipe\",\n"
        "      \"description\": \"Brief description\",\n"
        "      \"estimated_time\": \"30 minutes\",\n"
        "      \"difficulty\": \"Easy/Medium/Hard\",\n"
        "      \"cuisine_type\": \"Italian/Asian/etc\",\n"
        "      \"serves\": \"4 people\",\n"
        "      \"food_safety_summary\": \"Safety notes\"\n"
        "    },\n"
        "    \"details\": {\n"
        "      \"ingredients\": [\"ingredient 1\", \"ingredient 2\"],\n"
        "      \"equipment_needed\": [\"pan\", \"oven\"],\n"
        "      \"prep_time\": \"10 minutes\",\n"
        "      \"cook_time\": \"20 minutes\",\n"
        "      \"method_overview\": \"Brief cooking method\",\n"
        "      \"key_techniques\": [\"searing\", \"baking\"],\n"
        "      \"food_safety_details\": {\n"
        "        \"temperature_guidelines\": \"Cook to 165°F\",\n"
        "        \"storage_instructions\": \"Refrigerate leftovers\",\n"
        "        \"handling_tips\": \"Wash hands after handling\"\n"
        "      },\n"
        "      \"dietary_info\": [\"gluten-free\", \"dairy-free\"],\n"
        "      \"substitutions\": [\"Use olive oil instead of butter\"],\n"
        "      \"chef_tips\": [\"Let meat rest before cutting\"],\n"
        "      \"serving_suggestions\": [\"Serve with salad\"],\n"
        "      \"make_ahead_notes\": \"Can be prepared 1 day ahead\",\n"
        "      \"troubleshooting\": [\"If too dry, add more liquid\"]\n"
        "    },\n"
        "    \"sous_chef_format\": {\n"
        "      \"name\": \"Recipe Title\",\n"
        "      \"steps\": {\n"
        "        \"1\": \"First step with specific instructions\",\n"
        "        \"2\": \"Second step with timing (e.g., 'Bake for 20 minutes')\",\n"
        "        \"3\": \"Continue until complete\"\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "]\n\n"
        "IMPORTANT FOR SOUS_CHEF_FORMAT:\n"
        "• Break down the cooking method into clear, sequential numbered steps\n"
        "• Each step should be actionable and specific\n"
        "• Include timing information where relevant (e.g., 'Bake for 20 minutes', 'Simmer for 15 minutes')\n"
        "• Keep steps concise but complete\n"
        "• Number steps as strings (\"1\", \"2\", \"3\", etc.)\n"
        "• Make sure the steps flow logically from start to finish\n"
        "• Include any timer-based steps clearly (the sous chef agent will detect these)\n\n"
    ),
    description="Suggest cooking recipes based on input ingredients",
    tools=[web_search_recipes_tool]
)

async def smart_recipe_search_handler(ingredients: List[str]) -> Dict:
    """
    Search for recipes and return structured response.
    
    Args:
        ingredients: List of ingredients to search for
        
    Returns:
        Dictionary with 'recipes' key containing list of recipe dictionaries
    """
    # 1) Start an in‑memory session
    session_svc = InMemorySessionService()
    session = await session_svc.create_session(
        app_name="recipe_suggestor_app",
        user_id="anonymous",
        session_id=None
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

    # 4) Run the agent and parse the JSON response
    raw_response = None
    async for evt in runner.run_async(
        user_id="anonymous",
        session_id=session.id,
        new_message=user_msg
    ):
        if evt.is_final_response():
            raw_response = evt.content.parts[0].text
            break

    if not raw_response:
        return {"recipes": []}

    # 5) Clean and parse the JSON response
    try:
        cleaned = clean_json_response(raw_response)
        recipes = json.loads(cleaned)
        return {"recipes": recipes}
        
    except Exception as e:
        print(f"Error parsing response: {e}")
        print(f"Raw response preview: {raw_response[:500] if raw_response else 'None'}")
        return {"recipes": []}

def clean_json_response(txt: str) -> str:
    """Clean the JSON response from the agent"""
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

def extract_sous_chef_format(recipe_response: Dict, recipe_index: int = 0) -> Dict:
    """
    Extract just the sous_chef_format from a recipe response.
    
    Args:
        recipe_response: The response from the agent
        recipe_index: Which recipe to extract (default: first recipe)
        
    Returns:
        Dictionary with 'name' and 'steps' keys or None if not found
    """
    recipes = recipe_response.get("recipes", [])
    if recipes and len(recipes) > recipe_index:
        return recipes[recipe_index].get("sous_chef_format")
    return None

# Alias for backward compatibility
extract_sous_chef_dict = extract_sous_chef_format

async def main():
    """
    Test function to demonstrate the recipe suggester.
    """
    print("🍳 Testing Recipe Suggester Agent")
    print("=" * 60)
    
    # Test ingredients
    test_ingredients = [
        ["chicken", "pasta", "garlic"],
        ["beef", "potatoes", "onions"],
        ["salmon", "rice", "vegetables"]
    ]
    
    for i, ingredients in enumerate(test_ingredients, 1):
        print(f"\n📋 Test {i}: Searching for recipes with {', '.join(ingredients)}")
        print("-" * 40)
        
        try:
            # Get response
            response = await smart_recipe_search_handler(ingredients)
            recipes = response.get("recipes", [])
            
            if recipes:
                print(f"✅ Found {len(recipes)} recipes!")
                
                # Display each recipe summary
                for j, recipe in enumerate(recipes, 1):
                    summary = recipe.get("summary", {})
                    print(f"\n🍽️  Recipe {j}: {summary.get('title', 'Unknown')}")
                    print(f"   Difficulty: {summary.get('difficulty', 'Unknown')}")
                    print(f"   Time: {summary.get('estimated_time', 'Unknown')}")
                    print(f"   Cuisine: {summary.get('cuisine_type', 'Unknown')}")
                    print(f"   Serves: {summary.get('serves', 'Unknown')}")
                    
                    # Show sous chef format
                    sous_chef = recipe.get("sous_chef_format", {})
                    steps = sous_chef.get("steps", {})
                    print(f"   📝 Sous Chef Steps ({len(steps)} steps):")
                    for step_num, step_desc in list(steps.items())[:3]:  # Show first 3 steps
                        print(f"      {step_num}. {step_desc[:80]}{'...' if len(step_desc) > 80 else ''}")
                    if len(steps) > 3:
                        print(f"      ... and {len(steps) - 3} more steps")
                
                # Test extraction function
                print("\n🔧 Testing extraction function:")
                sous_chef_format = extract_sous_chef_format(response, 0)
                if sous_chef_format:
                    print(f"   ✅ extract_sous_chef_format(): {sous_chef_format.get('name', 'Unknown')} ({len(sous_chef_format.get('steps', {}))} steps)")
                
            else:
                print("❌ No recipes found")
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 60)
    
    print("🎉 Testing completed!")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())