from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv
from agents.suggester_agent import smart_recipe_search_handler
from typing import Optional
from datetime import datetime
import json

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class IngredientList(BaseModel):
    ingredients: List[str]

class LikeRecipe(BaseModel):
    recipe_id: str
    user_id: str
    cuisine_type: Optional[str] = None
    difficulty: Optional[str] = None
    estimated_time: Optional[str] = None
    ingredients: Optional[List[str]] = None
    link: Optional[str] = None


@app.post("/agent/smart-search")
async def smart_recipe_search(payload: IngredientList):
    return await smart_recipe_search_handler(payload.ingredients)

@app.post("/agent/like-recipe")
async def like_recipe(payload: LikeRecipe):
    """Store a liked recipe with user preferences"""

    # Example user_preferences dictionary (should be replaced with actual storage logic)
    global user_preferences
    if "liked_recipes" not in user_preferences:
        user_preferences["liked_recipes"] = []

    # Add to liked recipes if not already present
    existing_ids = [recipe["recipe_id"] for recipe in user_preferences["liked_recipes"]]

    if payload.recipe_id not in existing_ids:
        liked_recipe = {
            "recipe_id": payload.recipe,
            "title": payload.title,
            "cuisine_type": payload.cuisine_type,
            "difficulty": payload.difficulty,
            "estimated_time": payload.estimated_time,
            "ingredients": payload.ingredients or [],
            "link": payload.link,
            "liked_at": datetime.now().isoformat()
        }

        user_preferences["liked_recipes"].append(liked_recipe)

        #Update preferences
        _update_preference_patterns(liked_recipe)

        print(f"Recipe '{payload.title}' liked and added to preferences.")
        print(f"Total liked recipes: {len(user_preferences['liked_recipes'])}")

        return {
            "message": True,
            "message": f"Recipe '{payload.title}' added to your favorites.",
            "total_likes": len(user_preferences["liked_recipes"])
        }
    
    else:
        return {
            "success": True,
            "message": f"Recipe is already in your favorites.",
            "total_likes": len(user_preferences["liked_recipes"])
        }
    
@app.delete("/agent/unlike-recipe/{recipe_id}")
async def unlike_recipe(recipe_id: str):
    """Remove a recipe from liked recipes"""
    initial_count = len(user_preferences["liked_recipes"])
    user_preferences["liked_recipes"] = [
        recipe for recipe in user_preferences["liked_recipes"] 
        if recipe["recipe_id"] != recipe_id
    ]
    
    removed = initial_count > len(user_preferences["liked_recipes"])
    
    if removed:
        # Rebuild preference patterns
        _rebuild_preference_patterns()
        
    return {
        "success": removed,
        "message": "Recipe removed from favorites" if removed else "Recipe not found in favorites",
        "total_likes": len(user_preferences["liked_recipes"])
    }

@app.get("/agent/liked-recipes")
async def get_liked_recipes():
    """Get all liked recipes"""
    return {
        "liked_recipes": user_preferences["liked_recipes"],
        "total": len(user_preferences["liked_recipes"]),
        "preferences": user_preferences["preference_patterns"]
    }

@app.get("/agent/preferences")
async def get_user_preferences():
    """Get user preference patterns"""
    return user_preferences["preference_patterns"]

def _update_preference_patterns(liked_recipe):
    """Update preference patterns based on a newly liked recipe"""
    patterns = user_preferences["preference_patterns"]
    
    # Update cuisine preferences
    if liked_recipe.get("cuisine_type"):
        cuisine = liked_recipe["cuisine_type"]
        patterns["cuisines"][cuisine] = patterns["cuisines"].get(cuisine, 0) + 1
    
    # Update difficulty preferences
    if liked_recipe.get("difficulty"):
        difficulty = liked_recipe["difficulty"]
        patterns["difficulty_levels"][difficulty] = patterns["difficulty_levels"].get(difficulty, 0) + 1
    
    # Update ingredient preferences
    if liked_recipe.get("ingredients"):
        for ingredient in liked_recipe["ingredients"]:
            ingredient_lower = ingredient.lower()
            patterns["ingredients"][ingredient_lower] = patterns["ingredients"].get(ingredient_lower, 0) + 1
    
    # Update cooking time preferences
    if liked_recipe.get("estimated_time"):
        time_category = _categorize_cooking_time(liked_recipe["estimated_time"])
        patterns["cooking_times"][time_category] = patterns["cooking_times"].get(time_category, 0) + 1

def _rebuild_preference_patterns():
    """Rebuild preference patterns from scratch"""
    patterns = {
        "cuisines": {},
        "ingredients": {},
        "difficulty_levels": {},
        "cooking_times": {}
    }
    
    for recipe in user_preferences["liked_recipes"]:
        _update_preference_patterns(recipe)

def _categorize_cooking_time(time_str):
    """Categorize cooking time into buckets"""
    if not time_str:
        return "unknown"
    
    time_lower = time_str.lower()
    if "minute" in time_lower:
        try:
            minutes = int(''.join(filter(str.isdigit, time_str)))
            if minutes <= 15:
                return "quick (≤15 min)"
            elif minutes <= 30:
                return "medium (16-30 min)"
            elif minutes <= 60:
                return "longer (31-60 min)"
            else:
                return "extended (>60 min)"
        except:
            pass
    
    if any(word in time_lower for word in ["quick", "fast", "easy"]):
        return "quick (≤15 min)"
    elif any(word in time_lower for word in ["hour", "slow"]):
        return "extended (>60 min)"
    
    return "medium (16-30 min)"

@app.get("/")
def home():
    return {"message": "Gemini-powered backend is up and running!"}
