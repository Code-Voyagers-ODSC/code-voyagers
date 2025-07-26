import warnings
import logging
import os
import uuid
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from dotenv import load_dotenv
from pyprojroot.here import here

# Import Google ADK components
from google.adk.agents import Agent
from google.adk.tools import ToolContext
from google.adk.tools.base_tool import BaseTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.genai.types import Content, Part
from loguru import logger

# Import agents
from agents.suggester_agent import smart_recipe_search_handler, extract_sous_chef_dict

# Recipe Memory Service
class RecipeMemoryService:
    def __init__(self):
        self.memory_service = InMemoryMemoryService()
        self.session_service = InMemorySessionService()
    
    async def add_session_to_memory(self, session):
        """Add a completed cooking session to memory"""
        await self.memory_service.add_session_to_memory(session)
    
    def get_memory_service(self):
        return self.memory_service
    
    def get_session_service(self):
        return self.session_service

# Suppress warnings
warnings.filterwarnings("ignore")
logging.getLogger("google").setLevel(logging.ERROR)

# Configure logger
logger.remove()
logger.add("cooking_sessions.log", rotation="500 MB", level="DEBUG")

# Load environment
load_dotenv(dotenv_path=here(".env"))
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set")
genai.configure(api_key=api_key)

# Constants
MODEL = "gemini-1.5-flash"
COMPLETION_PHRASE = "The recipe is finished."
APP_NAME = "cooking_assistant"

# FastAPI app
app = FastAPI(title="Cooking Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8082"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global services
recipe_memory_service = RecipeMemoryService()
active_runners: Dict[str, Runner] = {}

# Pydantic models
class IngredientList(BaseModel):
    ingredients: List[str]

class StartCookingRequest(BaseModel):
    recipe_index: int = 0  # Which recipe from search results to use
    ingredients: List[str]  # Original ingredients searched

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

# Enhanced timer tool for web context
def web_timer_tool(time_in_seconds: int, tool_context: ToolContext) -> dict:
    """Timer tool adapted for web - stores timer state instead of blocking"""
    logger.info(f"Web timer tool called for {time_in_seconds} seconds")
    
    try:
        if time_in_seconds < 0:
            raise ValueError("Time must be positive")
        
        # Store timer state in session
        tool_context.state["timer_active"] = True
        tool_context.state["timer_duration"] = time_in_seconds
        tool_context.state["timer_start_time"] = datetime.now().isoformat()
        
        logger.info(f"Timer state stored: {time_in_seconds} seconds")
        return {
            "status": "timer_started", 
            "duration": time_in_seconds, 
            "message": f"Timer started for {time_in_seconds} seconds"
        }
        
    except Exception as e:
        logger.error(f"Timer error: {e}")
        return {"status": "error", "message": str(e)}

# Recipe manager tool class
class WebRecipeManagerTool(BaseTool):
    """Recipe manager adapted for web sessions"""
    
    def __init__(self):
        super().__init__(name="recipe_manager", description="Manages recipe steps for web sessions")

    def get_current_step(self, tool_context: ToolContext) -> dict:
        """Get current recipe step"""
        recipe_steps = tool_context.state.get("recipe_steps", {})
        current_index = tool_context.state.get("step_index", 0)
        
        if not recipe_steps:
            return {"step": "No recipe loaded", "step_number": 0, "is_complete": True}
        
        step_keys = sorted([int(k) for k in recipe_steps.keys()])
        
        if current_index >= len(step_keys):
            tool_context.state["recipe_completed"] = True
            return {"step": COMPLETION_PHRASE, "step_number": "complete", "is_complete": True}

        current_step_key = str(step_keys[current_index])
        current_step_text = recipe_steps[current_step_key]
        
        tool_context.state["current_step_text"] = current_step_text
        tool_context.state["current_step_number"] = current_index + 1

        logger.info(f"Current step {current_index + 1}: {current_step_text}")
        return {
            "step": current_step_text, 
            "step_number": current_index + 1,
            "is_complete": False
        }

    def advance_step(self, tool_context: ToolContext) -> dict:
        """Advance to next step"""
        current_index = tool_context.state.get("step_index", 0)
        recipe_steps = tool_context.state.get("recipe_steps", {})
        step_keys = sorted([int(k) for k in recipe_steps.keys()])
        
        new_index = current_index + 1
        tool_context.state["step_index"] = new_index
        
        if new_index >= len(step_keys):
            tool_context.state["recipe_completed"] = True
            logger.info("Recipe completed!")
            
        logger.info(f"Advanced from step {current_index + 1} to step {new_index + 1}")
        return {"status": "success", "message": f"Advanced to step {new_index + 1}"}

def wait_for_user_confirmation(tool_context: ToolContext) -> dict:
    """Signal that we're waiting for user input"""
    return {"status": "waiting", "message": "Waiting for user input"}

def exit_loop(tool_context: ToolContext):
    """Mark recipe as completed"""
    logger.info("Recipe completion triggered")
    tool_context.state["recipe_completed"] = True
    return {"status": "success", "message": "Recipe completed"}

# Import timer parsing function from original sous_chef_agent
import re

def parse_timer_duration(text: str) -> dict:
    """Parse timer duration from recipe text"""
    patterns = [
        (r'(\d+)-second', 1),
        (r'(\d+)\s*second', 1),
        (r'(\d+)-minute', 60),
        (r'(\d+)\s*minute', 60),
        (r'(\d+)-hour', 3600),
        (r'(\d+)\s*hour', 3600),
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            duration_num = int(match.group(1))
            duration_seconds = duration_num * multiplier
            unit = "second" if multiplier == 1 else "minute" if multiplier == 60 else "hour"
            unit += "s" if duration_num != 1 else ""
            
            return {
                "status": "success",
                "duration_seconds": duration_seconds,
                "duration_text": f"{duration_num} {unit}",
                "original_match": match.group(0)
            }
    
    return {"status": "not_found", "message": "No timer duration found"}

# Create the sous chef agent
recipe_manager_tool = WebRecipeManagerTool()

sous_chef_agent = Agent(
    name="WebSousChefAgent",
    model=MODEL,
    tools=[
        recipe_manager_tool.get_current_step, 
        recipe_manager_tool.advance_step, 
        parse_timer_duration,
        web_timer_tool, 
        wait_for_user_confirmation,
        exit_loop
    ],
    instruction="""You are a friendly Sous Chef helping users cook step by step through a web interface.

WORKFLOW:
1. **First interaction**: Greet user, call get_current_step, present step clearly, call wait_for_user_confirmation
2. **When user says 'next'**: Call advance_step, get_current_step, present new step, handle timers if needed
3. **Timer handling**: When step mentions timing, call parse_timer_duration, then web_timer_tool to start timer
4. **Completion**: When get_current_step returns completion phrase, call exit_loop and congratulate user

TIMER WORKFLOW:
- Parse timer duration from step text
- Start timer with web_timer_tool 
- Inform user that timer is running and they can continue when ready

MESSAGING:
- Be encouraging and friendly
- Keep responses concise but helpful
- Don't repeat confirmation messages
- Include timing information clearly in steps"""
)

# Helper functions
def get_timer_info(session_state: dict) -> Optional[TimerInfo]:
    """Get current timer information from session state"""
    if not session_state.get("timer_active"):
        return TimerInfo(active=False)
    
    start_time_str = session_state.get("timer_start_time")
    duration = session_state.get("timer_duration")
    
    if not start_time_str or not duration:
        return TimerInfo(active=False)
    
    start_time = datetime.fromisoformat(start_time_str)
    elapsed = (datetime.now() - start_time).total_seconds()
    remaining = max(0, duration - elapsed)
    
    # If timer is done, mark as inactive
    if remaining <= 0:
        session_state["timer_active"] = False
        return TimerInfo(active=False)
    
    return TimerInfo(
        active=True,
        duration_seconds=duration,
        start_time=start_time,
        remaining_seconds=int(remaining)
    )

# API Endpoints

@app.get("/")
def home():
    return {"message": "Cooking Assistant API is running!"}

@app.post("/agent/smart-search")
async def smart_recipe_search(payload: IngredientList):
    """Search for recipes based on ingredients"""
    return await smart_recipe_search_handler(payload.ingredients)

@app.post("/cooking/start")
async def start_cooking_session(request: StartCookingRequest) -> CookingResponse:
    """Start a new cooking session with a selected recipe"""
    try:
        # Get recipe suggestions first
        recipe_response = await smart_recipe_search_handler(request.ingredients)
        
        if not recipe_response.recipes or len(recipe_response.recipes) <= request.recipe_index:
            raise HTTPException(status_code=404, detail="Recipe not found")
        
        # Extract the selected recipe in sous chef format
        selected_recipe = recipe_response.recipes[request.recipe_index]
        sous_chef_recipe = {
            "name": selected_recipe.sous_chef_format.name,
            "steps": selected_recipe.sous_chef_format.steps
        }
        
        # Create new cooking session
        session_id = str(uuid.uuid4())
        initial_state = {
            "step_index": 0,
            "recipe_completed": False,
            "recipe_name": sous_chef_recipe["name"],
            "recipe_steps": sous_chef_recipe["steps"],
            "timer_active": False
        }
        
        session = await recipe_memory_service.get_session_service().create_session(
            app_name=APP_NAME,
            user_id="web_user",
            session_id=session_id,
            state=initial_state
        )
        
        # Create runner for this session
        runner = Runner(
            agent=sous_chef_agent,
            session_service=recipe_memory_service.get_session_service(),
            app_name=APP_NAME
        )
        active_runners[session_id] = runner
        
        # Start the cooking session with greeting
        greeting_content = Content(parts=[Part(text="Hello, let's start cooking!")], role="user")
        
        response_text = ""
        waiting_for_user = False
        
        async for event in runner.run_async(
            user_id="web_user",
            session_id=session_id,
            new_message=greeting_content
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text
                    elif part.function_call and part.function_call.name == "wait_for_user_confirmation":
                        waiting_for_user = True
            
            if event.is_final_response():
                break
        
        # Get updated session state
        updated_session = await recipe_memory_service.get_session_service().get_session(
            app_name=APP_NAME, user_id="web_user", session_id=session_id
        )
        
        timer_info = get_timer_info(updated_session.state)
        
        return CookingResponse(
            session_id=session_id,
            message=response_text,
            waiting_for_user=waiting_for_user,
            timer_info=timer_info,
            recipe_completed=updated_session.state.get("recipe_completed", False)
        )
        
    except Exception as e:
        logger.error(f"Error starting cooking session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cooking/interact")
async def cooking_interaction(request: CookingInteraction) -> CookingResponse:
    """Handle user interaction during cooking"""
    try:
        # Get the runner for this session
        runner = active_runners.get(request.session_id)
        if not runner:
            raise HTTPException(status_code=404, detail="Cooking session not found")
        
        # Send user message to agent
        user_content = Content(parts=[Part(text=request.message)], role="user")
        
        response_text = ""
        waiting_for_user = False
        timer_started = False
        
        async for event in runner.run_async(
            user_id="web_user",
            session_id=request.session_id,
            new_message=user_content
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text
                    elif part.function_call:
                        if part.function_call.name == "wait_for_user_confirmation":
                            waiting_for_user = True
                        elif part.function_call.name == "web_timer_tool":
                            timer_started = True
            
            if event.is_final_response():
                break
        
        # Get updated session state
        session = await recipe_memory_service.get_session_service().get_session(
            app_name=APP_NAME, user_id="web_user", session_id=request.session_id
        )
        
        timer_info = get_timer_info(session.state)
        recipe_completed = session.state.get("recipe_completed", False)
        
        # If recipe completed, save to memory and clean up
        if recipe_completed and request.session_id in active_runners:
            await recipe_memory_service.add_session_to_memory(session)
            del active_runners[request.session_id]
        
        return CookingResponse(
            session_id=request.session_id,
            message=response_text,
            waiting_for_user=waiting_for_user,
            timer_info=timer_info,
            recipe_completed=recipe_completed
        )
        
    except Exception as e:
        logger.error(f"Error in cooking interaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cooking/{session_id}/status")
async def get_cooking_status(session_id: str):
    """Get current status of a cooking session"""
    try:
        session = await recipe_memory_service.get_session_service().get_session(
            app_name=APP_NAME, user_id="web_user", session_id=session_id
        )
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        timer_info = get_timer_info(session.state)
        
        return {
            "session_id": session_id,
            "recipe_name": session.state.get("recipe_name"),
            "current_step": session.state.get("current_step_number", 0),
            "timer_info": timer_info,
            "recipe_completed": session.state.get("recipe_completed", False)
        }
        
    except Exception as e:
        logger.error(f"Error getting session status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/cooking/{session_id}")
async def end_cooking_session(session_id: str):
    """End a cooking session"""
    try:
        # Remove from active runners
        if session_id in active_runners:
            del active_runners[session_id]
        
        return {"message": "Cooking session ended", "session_id": session_id}
        
    except Exception as e:
        logger.error(f"Error ending session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
