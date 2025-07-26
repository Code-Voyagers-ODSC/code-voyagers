# agents/suggester_agent.py

import json
import sys
import re
from typing import List, Dict
from dotenv import load_dotenv
from pyprojroot.here import here
from pydantic import BaseModel, Field

# Add project root to Python path using pyprojroot
project_root = here()
sys.path.insert(0, str(project_root))

from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

from src.tools.search_tool import web_search_recipes_tool

load_dotenv(here(".env"))

# Define Pydantic models for structured output
class RecipeSummary(BaseModel):
    title: str = Field(description="The recipe title")
    link: str = Field(description="URL link to the original recipe")
    description: str = Field(description="Brief description of the recipe")
    estimated_time: str = Field(description="Total estimated cooking time")
    difficulty: str = Field(description="Difficulty level (Easy, Medium, Hard)")
    cuisine_type: str = Field(description="Type of cuisine")
    serves: str = Field(description="Number of servings")
    food_safety_summary: str = Field(description="Brief food safety notes")

class FoodSafetyDetails(BaseModel):
    temperature_guidelines: str = Field(description="Safe cooking temperatures")
    storage_instructions: str = Field(description="How to store the dish")
    handling_tips: str = Field(description="Safe food handling tips")

class RecipeDetails(BaseModel):
    ingredients: List[str] = Field(description="List of ingredients needed")
    equipment_needed: List[str] = Field(description="Kitchen equipment required")
    prep_time: str = Field(description="Preparation time")
    cook_time: str = Field(description="Cooking time")
    method_overview: str = Field(description="Brief overview of cooking method")
    key_techniques: List[str] = Field(description="Key cooking techniques used")
    food_safety_details: FoodSafetyDetails
    dietary_info: List[str] = Field(description="Dietary information (vegetarian, gluten-free, etc.)")
    substitutions: List[str] = Field(description="Possible ingredient substitutions")
    chef_tips: List[str] = Field(description="Professional cooking tips")
    serving_suggestions: List[str] = Field(description="How to serve the dish")
    make_ahead_notes: str = Field(description="Notes on preparing ahead of time")
    troubleshooting: List[str] = Field(description="Common problems and solutions")

class SousChefFormat(BaseModel):
    name: str = Field(description="Recipe name for the sous chef")
    steps: Dict[str, str] = Field(description="Numbered cooking steps as string keys with step descriptions")

class Recipe(BaseModel):
    id: str = Field(description="Unique recipe identifier")
    summary: RecipeSummary
    details: RecipeDetails
    sous_chef_format: SousChefFormat

class RecipeResponse(BaseModel):
    recipes: List[Recipe] = Field(description="List of 3-4 best matching recipes")

# Define the Agent WITHOUT structured output (since we're using tools)
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
    # Note: No output_schema because we're using tools
)

async def smart_recipe_search_handler(ingredients: List[str]) -> RecipeResponse:
    """
    Search for recipes and return structured response.
    
    Args:
        ingredients: List of ingredients to search for
        
    Returns:
        RecipeResponse object with structured recipe data
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

    # 4) Run the agent and parse the JSON response manually
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
        return RecipeResponse(recipes=[])

    # 5) Clean and parse the JSON response, then convert to Pydantic
    try:
        cleaned = clean_json_response(raw_response)
        recipes_dict = json.loads(cleaned)
        
        # Convert dictionary to Pydantic models
        recipes = []
        for recipe_dict in recipes_dict:
            recipe = Recipe(**recipe_dict)
            recipes.append(recipe)
            
        return RecipeResponse(recipes=recipes)
        
    except Exception as e:
        print(f"Error parsing response: {e}")
        print(f"Raw response preview: {raw_response[:500] if raw_response else 'None'}")
        return RecipeResponse(recipes=[])

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

def extract_sous_chef_format(recipe_response: RecipeResponse, recipe_index: int = 0) -> SousChefFormat:
    """
    Extract just the sous_chef_format from a structured recipe response.
    
    Args:
        recipe_response: The structured response from the agent
        recipe_index: Which recipe to extract (default: first recipe)
        
    Returns:
        SousChefFormat object ready for the sous chef agent
    """
    if recipe_response.recipes and len(recipe_response.recipes) > recipe_index:
        return recipe_response.recipes[recipe_index].sous_chef_format
    return None

def extract_sous_chef_dict(recipe_response: RecipeResponse, recipe_index: int = 0) -> dict:
    """
    Extract sous chef format as a plain dictionary (for compatibility with existing code).
    
    Args:
        recipe_response: The structured response from the agent
        recipe_index: Which recipe to extract (default: first recipe)
        
    Returns:
        Dictionary with 'name' and 'steps' keys
    """
    sous_chef_format = extract_sous_chef_format(recipe_response, recipe_index)
    if sous_chef_format:
        return {
            "name": sous_chef_format.name,
            "steps": {k: v for k, v in sous_chef_format.steps.items()}
        }
    return None

# Example usage:
async def example_usage():
    # Get structured response
    response = await smart_recipe_search_handler(["chicken", "pasta", "garlic"])
    
    # Access structured data directly
    print(f"Found {len(response.recipes)} recipes")
    for i, recipe in enumerate(response.recipes):
        print(f"Recipe {i+1}: {recipe.summary.title}")
        print(f"Difficulty: {recipe.summary.difficulty}")
        print(f"Estimated time: {recipe.summary.estimated_time}")
    
    # Extract for sous chef agent (as dictionary)
    sous_chef_recipe = extract_sous_chef_dict(response, recipe_index=0)
    if sous_chef_recipe:
        print(f"Sous chef recipe: {sous_chef_recipe['name']}")
        print(f"Number of steps: {len(sous_chef_recipe['steps'])}")
    
    return response

# For backward compatibility, also provide a function that returns the old format
async def smart_recipe_search_handler_dict(ingredients: List[str]) -> dict:
    """
    Legacy function that returns dictionary format for backward compatibility.
    """
    structured_response = await smart_recipe_search_handler(ingredients)
    
    # Convert to dictionary format
    recipes_dict = []
    for recipe in structured_response.recipes:
        recipe_dict = {
            "id": recipe.id,
            "summary": recipe.summary.model_dump(),
            "details": recipe.details.model_dump(),
            "sous_chef_format": recipe.sous_chef_format.model_dump()
        }
        recipes_dict.append(recipe_dict)
    
    return {"recipes": recipes_dict}

async def main():
    """
    Test function to demonstrate the structured output recipe suggester.
    """
    print("🍳 Testing Recipe Suggester Agent with Structured Output")
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
            # Get structured response
            response = await smart_recipe_search_handler(ingredients)
            
            if response.recipes:
                print(f"✅ Found {len(response.recipes)} recipes!")
                
                # Display each recipe summary
                for j, recipe in enumerate(response.recipes, 1):
                    print(f"\n🍽️  Recipe {j}: {recipe.summary.title}")
                    print(f"   Difficulty: {recipe.summary.difficulty}")
                    print(f"   Time: {recipe.summary.estimated_time}")
                    print(f"   Cuisine: {recipe.summary.cuisine_type}")
                    print(f"   Serves: {recipe.summary.serves}")
                    
                    # Show sous chef format
                    sous_chef = recipe.sous_chef_format
                    print(f"   📝 Sous Chef Steps ({len(sous_chef.steps)} steps):")
                    for step_num, step_desc in list(sous_chef.steps.items())[:3]:  # Show first 3 steps
                        print(f"      {step_num}. {step_desc[:80]}{'...' if len(step_desc) > 80 else ''}")
                    if len(sous_chef.steps) > 3:
                        print(f"      ... and {len(sous_chef.steps) - 3} more steps")
                
                # Test extraction functions
                print("\n🔧 Testing extraction functions:")
                sous_chef_format = extract_sous_chef_format(response, 0)
                if sous_chef_format:
                    print(f"   ✅ extract_sous_chef_format(): {sous_chef_format.name}")
                
                sous_chef_dict = extract_sous_chef_dict(response, 0)
                if sous_chef_dict:
                    print(f"   ✅ extract_sous_chef_dict(): {sous_chef_dict['name']} ({len(sous_chef_dict['steps'])} steps)")
                
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