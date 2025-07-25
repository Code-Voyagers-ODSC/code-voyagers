# agents/suggester_agent.py

import json
from typing import List, Dict
from dotenv import load_dotenv
from pyprojroot.here import here
from pydantic import BaseModel, Field

from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

from tools.search_tool import web_search_recipes_tool

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

# Define the Agent with structured output
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
    tools=[web_search_recipes_tool],
    response_schema=RecipeResponse  # This enables structured output!
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

    # 4) Run the agent - it will return structured data automatically
    structured_response = None
    async for evt in runner.run_async(
        user_id="anonymous",
        session_id=session.id,
        new_message=user_msg
    ):
        if evt.is_final_response():
            # With structured output, the response is already parsed!
            if hasattr(evt, 'structured_response') and evt.structured_response:
                structured_response = evt.structured_response
            else:
                # Fallback: try to parse from text if structured response not available
                try:
                    response_text = evt.content.parts[0].text
                    response_dict = json.loads(response_text)
                    structured_response = RecipeResponse(**response_dict)
                except Exception as e:
                    return RecipeResponse(recipes=[])  # Return empty response on error
            break

    if not structured_response:
        return RecipeResponse(recipes=[])

    return structured_response

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