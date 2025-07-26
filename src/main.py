import warnings
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from dotenv import load_dotenv
from pyprojroot.here import here
from loguru import logger

# Add project root to path for imports
project_root = here()
sys.path.insert(0, str(project_root))

# Import Google ADK components
from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService

# Import agents and handlers
from agents.suggester_agent import smart_recipe_search_handler
from agents.sous_chef_agent import CookingAgentHandler

warnings.filterwarnings("ignore")
logging.getLogger("google").setLevel(logging.ERROR)

logger.remove()
logger.add("cooking_sessions.log", rotation="500 MB", level="DEBUG")

load_dotenv(dotenv_path=here(".env"))
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set")
genai.configure(api_key=api_key)

app = FastAPI(title="Cooking Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8082"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared recipe storage and memory service
class RecipeMemoryService:
    def __init__(self):
        self.memory_service = InMemoryMemoryService()
        self.session_service = InMemorySessionService()
        self.stored_recipes = {}
    
    async def add_session_to_memory(self, session):
        """Add a completed cooking session to memory"""
        await self.memory_service.add_session_to_memory(session)
    
    def get_memory_service(self):
        return self.memory_service
    
    def get_session_service(self):
        return self.session_service
    
    def store_recipe(self, recipe_id: str, recipe_data: dict):
        self.stored_recipes[recipe_id] = recipe_data
    
    def get_recipe(self, recipe_id: str):
        return self.stored_recipes.get(recipe_id)

# Initialize shared services
recipe_memory_service = RecipeMemoryService()
cooking_handler = CookingAgentHandler(
    memory_service=recipe_memory_service.get_memory_service(),
    session_service=recipe_memory_service.get_session_service()
)

# Pydantic models
class IngredientList(BaseModel):
    ingredients: List[str]

class StartCookingRequest(BaseModel):
    id: str

class CookingInteraction(BaseModel):
    session_id: str
    message: str

class TimerInfo(BaseModel):
    active: bool
    duration_seconds: Optional[int] = None
    start_time: Optional[datetime] = None
    remaining_seconds: Optional[int] = None

class CookingResponse(BaseModel):
    session_id: str
    message: str
    waiting_for_user: bool = False
    timer_info: Optional[TimerInfo] = None
    recipe_completed: bool = False


def get_timer_info(session_state: dict) -> Optional[TimerInfo]:
    if not session_state.get("timer_active"):
        if session_state.get("timer_completed") and not session_state.get(
            "timer_completion_notified"
        ):
            return TimerInfo(
                active=False,
                duration_seconds=session_state.get("timer_duration"),
                remaining_seconds=0,
            )
        return TimerInfo(active=False)

    start_time_str = session_state.get("timer_start_time")
    duration = session_state.get("timer_duration")

    if not start_time_str or not duration:
        session_state["timer_active"] = False
        return TimerInfo(active=False)

    try:
        start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        remaining = max(0, duration - elapsed)

        if remaining <= 0:
            session_state["timer_active"] = False
            session_state["timer_completed"] = True
            return TimerInfo(
                active=False,
                duration_seconds=duration,
                start_time=start_time,
                remaining_seconds=0,
            )

        return TimerInfo(
            active=True,
            duration_seconds=duration,
            start_time=start_time,
            remaining_seconds=int(remaining),
        )

    except Exception as e:
        logger.error(f"Error calculating timer info: {e}")
        session_state["timer_active"] = False
        return TimerInfo(active=False)


@app.get("/")
def home():
    return {"message": "Cooking Assistant API is running!"}


@app.post("/agent/smart-search")
async def smart_recipe_search(payload: IngredientList):
    """Search for recipes and store them in cooking handler"""
    try:
        recipe_response = await smart_recipe_search_handler(payload.ingredients)
        
        # Store recipes in shared memory service
        for recipe in recipe_response["recipes"]:
            recipe_memory_service.store_recipe(recipe["id"], recipe["sous_chef_format"])
        
        return recipe_response
    except Exception as e:
        logger.error(f"Error in smart search: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cooking/start")
async def start_cooking_session(request: StartCookingRequest) -> CookingResponse:
    """Start cooking session with stored recipe"""
    try:
        recipe_data = recipe_memory_service.get_recipe(request.id)  # Get from shared memory service
        if not recipe_data:
            raise HTTPException(status_code=404, detail="Recipe not found. Please search for recipes first.")

        result = await cooking_handler.start_cooking_session(recipe_data)
        timer_info = get_timer_info(result["session_state"])

        return CookingResponse(
            session_id=result["session_id"],
            message=result["message"],
            waiting_for_user=result["waiting_for_user"],
            timer_info=timer_info,
            recipe_completed=result["recipe_completed"],
        )

    except Exception as e:
        logger.error(f"Error starting cooking session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cooking/interact")
async def cooking_interaction(request: CookingInteraction) -> CookingResponse:
    """Handle cooking interaction"""
    try:
        result = await cooking_handler.handle_interaction(request.session_id, request.message)
        timer_info = get_timer_info(result["session_state"])

        return CookingResponse(
            session_id=result["session_id"],
            message=result["message"],
            waiting_for_user=result["waiting_for_user"],
            timer_info=timer_info,
            recipe_completed=result["recipe_completed"],
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error in cooking interaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cooking/{session_id}/status")
async def get_cooking_status(session_id: str):
    """Get current status of a cooking session"""
    try:
        result = await cooking_handler.get_session_status(session_id)
        timer_info = get_timer_info(result["session_state"])

        return {
            "session_id": result["session_id"],
            "recipe_name": result["recipe_name"],
            "current_step": result["current_step"],
            "timer_info": timer_info,
            "recipe_completed": result["recipe_completed"],
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting session status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cooking/{session_id}/timer")
async def get_timer_status(session_id: str):
    """Get current timer status for a session"""
    try:
        result = await cooking_handler.get_session_status(session_id)
        timer_info = get_timer_info(result["session_state"])

        return {
            "session_id": session_id,
            "timer_info": timer_info,
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting timer status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/cooking/{session_id}")
async def end_cooking_session(session_id: str):
    """End a cooking session"""
    try:
        result = await cooking_handler.end_session(session_id)
        return result
    except Exception as e:
        logger.error(f"Error ending session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)