# main.py - Updated backend

import sys
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import asyncio
import uuid
from dotenv import load_dotenv

# Add src to Python path
sys.path.append(str(Path(__file__).parent))

# Import agents
from agents.suggester_agent import smart_recipe_search_handler_dict
from agents.ingredient_vision_agent import detect_ingredients_from_bytes

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8081",
        "http://localhost:3001",
        "*"  # For development only
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active cooking sessions (in production, use Redis)
cooking_sessions = {}

class IngredientList(BaseModel):
    ingredients: List[str]

class SousChefFormat(BaseModel):
    name: str
    steps: Dict[str, str]

class StartCookingRequest(BaseModel):
    sous_chef_format: SousChefFormat
    recipe_summary: Optional[Dict] = None  # Optional: for displaying recipe info

class CookingCommand(BaseModel):
    session_id: str
    command: str

@app.post("/agent/smart-search")
async def smart_recipe_search(payload: IngredientList):
    """Search for recipes using the suggester agent"""
    try:
        print(f"\n=== Recipe search for: {payload.ingredients} ===")
        
        # Use the dict version for backward compatibility
        result = await smart_recipe_search_handler_dict(payload.ingredients)
        
        # Debug logging
        if "recipes" in result:
            print(f"Found {len(result['recipes'])} recipes")
            for i, recipe in enumerate(result['recipes']):
                title = recipe.get('summary', {}).get('title', 'Unknown')
                has_steps = 'sous_chef_format' in recipe
                if has_steps:
                    num_steps = len(recipe['sous_chef_format'].get('steps', {}))
                    print(f"Recipe {i+1} ({title}): {num_steps} cooking steps")
                else:
                    print(f"Recipe {i+1} ({title}): No sous_chef_format!")
        
        return result
        
    except Exception as e:
        print(f"Error in smart search: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cooking/start")
async def start_cooking_session(request: StartCookingRequest):
    """Start a cooking session with the provided sous_chef_format"""
    try:
        # Extract the sous chef recipe directly from the request
        sous_chef_recipe = request.sous_chef_format.dict()
        
        # Validate that we have steps
        if not sous_chef_recipe.get("steps"):
            raise HTTPException(status_code=400, detail="Recipe has no cooking steps")
        
        # Create a session ID
        session_id = str(uuid.uuid4())
        
        # Initialize the cooking session
        cooking_sessions[session_id] = {
            "recipe": sous_chef_recipe,
            "recipe_summary": request.recipe_summary,  # Store summary if provided
            "step_index": 0,
            "completed": False,
            "waiting_for_timer": False
        }
        
        # Get the first step
        first_step = sous_chef_recipe["steps"].get("1", "No steps available")
        
        print(f"Started cooking session {session_id} for recipe: {sous_chef_recipe['name']}")
        print(f"Total steps: {len(sous_chef_recipe['steps'])}")
        
        return {
            "session_id": session_id,
            "recipe_name": sous_chef_recipe["name"],
            "total_steps": len(sous_chef_recipe["steps"]),
            "current_step": 1,
            "step_text": first_step,
            "message": f"Welcome! Let's cook {sous_chef_recipe['name']} together. Here's the first step.",
            "has_timer": _check_for_timer(first_step),
            "completed": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error starting cooking session: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/agent/detect-ingredients")
async def detect_ingredients(file: UploadFile = File(...)):
    """
    Accept an image upload, run the IngredientVisionAgent,
    and return a JSON list of detected ingredients.
    """
    img_bytes = await file.read()
    try:
        ingredients = detect_ingredients_from_bytes(img_bytes)
        return {"ingredients": ingredients}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/cooking/next")
async def next_cooking_step(command: CookingCommand):
    """Advance to the next cooking step"""
    
    if command.session_id not in cooking_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = cooking_sessions[command.session_id]
    recipe = session["recipe"]
    
    if session["completed"]:
        return {
            "message": "Recipe is already completed! Enjoy your meal! 🎉",
            "completed": True
        }
    
    # Advance to next step
    session["step_index"] += 1
    
    # Check if we've completed all steps
    if session["step_index"] >= len(recipe["steps"]):
        session["completed"] = True
        return {
            "message": f"Congratulations! You've completed {recipe['name']}. Enjoy your meal! 🎉",
            "completed": True,
            "recipe_name": recipe["name"]
        }
    
    # Get current step
    current_step_key = str(session["step_index"] + 1)
    current_step_text = recipe["steps"].get(current_step_key, "")
    
    if not current_step_text:
        session["completed"] = True
        return {
            "message": "Recipe completed!",
            "completed": True
        }
    
    # Check for timer in this step
    has_timer = _check_for_timer(current_step_text)
    
    return {
        "session_id": command.session_id,
        "current_step": session["step_index"] + 1,
        "total_steps": len(recipe["steps"]),
        "step_text": current_step_text,
        "has_timer": has_timer,
        "message": f"Step {session['step_index'] + 1} of {len(recipe['steps'])}",
        "completed": False
    }

@app.post("/cooking/timer/start")
async def start_timer(command: CookingCommand):
    """Start a timer for the current step"""
    
    if command.session_id not in cooking_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = cooking_sessions[command.session_id]
    current_step_key = str(session["step_index"] + 1)
    current_step_text = session["recipe"]["steps"].get(current_step_key, "")
    
    # Extract timer duration (simple implementation)
    duration = _extract_timer_duration(current_step_text)
    
    if duration:
        return {
            "timer_started": True,
            "duration_seconds": duration,
            "message": f"Timer started for {duration} seconds!"
        }
    else:
        return {
            "timer_started": False,
            "message": "No timer found in this step"
        }

@app.get("/cooking/status/{session_id}")
async def get_cooking_status(session_id: str):
    """Get the current status of a cooking session"""
    
    if session_id not in cooking_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = cooking_sessions[session_id]
    recipe = session["recipe"]
    
    current_step_key = str(session["step_index"] + 1)
    current_step_text = recipe["steps"].get(current_step_key, "Recipe completed!")
    
    return {
        "session_id": session_id,
        "recipe_name": recipe["name"],
        "current_step": session["step_index"] + 1,
        "total_steps": len(recipe["steps"]),
        "step_text": current_step_text,
        "completed": session["completed"],
        "has_timer": _check_for_timer(current_step_text) if not session["completed"] else False
    }

@app.get("/test-recipe")
async def test_recipe():
    """Test endpoint that returns a hardcoded recipe with cooking steps"""
    return {
        "recipes": [
            {
                "id": "recipe_1",
                "summary": {
                    "title": "Test Garlic Chicken Pasta",
                    "link": "https://example.com/test",
                    "description": "This is a test recipe to verify cooking steps display",
                    "estimated_time": "30 minutes",
                    "difficulty": "Beginner",
                    "cuisine_type": "Italian-American",
                    "serves": "4 servings",
                    "food_safety_summary": "Cook chicken to 165°F"
                },
                "details": {
                    "ingredients": [
                        "1 lb chicken breast",
                        "1 lb pasta",
                        "4 cloves garlic",
                        "1/4 cup olive oil"
                    ],
                    "equipment_needed": ["Large pot", "Large skillet"],
                    "prep_time": "10 minutes",
                    "cook_time": "20 minutes",
                    "method_overview": "Cook pasta, sauté chicken and garlic, combine",
                    "key_techniques": ["Sautéing", "Boiling"],
                    "food_safety_details": {
                        "temperature_guidelines": "Chicken: 165°F",
                        "storage_instructions": "Refrigerate within 2 hours",
                        "handling_tips": "Wash hands after handling raw chicken"
                    }
                },
                "sous_chef_format": {
                    "name": "Test Garlic Chicken Pasta",
                    "steps": {
                        "1": "Fill a large pot with water, add a generous pinch of salt, and bring to a boil over high heat",
                        "2": "While water is heating, cut chicken breast into bite-sized pieces and season with salt and pepper",
                        "3": "Heat olive oil in a large skillet over medium-high heat",
                        "4": "Add chicken pieces to the hot skillet and cook for 5-7 minutes until golden brown",
                        "5": "When water boils, add pasta and cook according to package directions (usually 8-10 minutes)",
                        "6": "While pasta cooks, mince the garlic cloves",
                        "7": "Push chicken to the side of skillet and add minced garlic, cook for 30 seconds until fragrant",
                        "8": "Drain pasta, reserving 1/2 cup of pasta water",
                        "9": "Add drained pasta to the skillet with chicken and garlic",
                        "10": "Toss everything together, adding pasta water if needed for moisture",
                        "11": "Serve hot with grated Parmesan cheese if desired"
                    }
                }
            }
        ]
    }

@app.get("/")
def home():
    return {"message": "Recipe API with integrated cooking assistant is running!"}

# Helper functions
def _check_for_timer(text: str) -> bool:
    """Check if text contains timer-related words"""
    timer_words = ["minute", "second", "timer", "bake", "simmer", "cook", "boil", "heat"]
    return any(word in text.lower() for word in timer_words)

def _extract_timer_duration(text: str) -> Optional[int]:
    """Extract timer duration in seconds from text"""
    import re
    
    # Look for patterns like "20 minutes", "30 seconds", etc.
    minutes_match = re.search(r'(\d+)\s*minute', text, re.IGNORECASE)
    seconds_match = re.search(r'(\d+)\s*second', text, re.IGNORECASE)
    
    total_seconds = 0
    if minutes_match:
        total_seconds += int(minutes_match.group(1)) * 60
    if seconds_match:
        total_seconds += int(seconds_match.group(1))
    
    return total_seconds if total_seconds > 0 else None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)