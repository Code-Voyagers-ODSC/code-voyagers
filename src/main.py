import warnings
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from dotenv import load_dotenv
from pyprojroot.here import here

# Add project root to path for imports
project_root = here()
sys.path.insert(0, str(project_root))

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

from tools.timer_tool import (
    parse_timer_duration,
    web_timer_tool,
    set_custom_timer,
    check_timer_completion,
)


class RecipeMemoryService:
    def __init__(self):
        self.memory_service = InMemoryMemoryService()
        self.session_service = InMemorySessionService()

    async def add_session_to_memory(self, session):
        await self.memory_service.add_session_to_memory(session)

    def get_memory_service(self):
        return self.memory_service

    def get_session_service(self):
        return self.session_service


warnings.filterwarnings("ignore")
logging.getLogger("google").setLevel(logging.ERROR)

logger.remove()
logger.add("cooking_sessions.log", rotation="500 MB", level="DEBUG")

load_dotenv(dotenv_path=here(".env"))
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set")
genai.configure(api_key=api_key)

MODEL = "gemini-1.5-flash"
COMPLETION_PHRASE = "The recipe is finished."
APP_NAME = "cooking_assistant"

app = FastAPI(title="Cooking Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8082"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

recipe_memory_service = RecipeMemoryService()
active_runners: Dict[str, Runner] = {}


# Pydantic models
class IngredientList(BaseModel):
    ingredients: List[str]


class StartCookingRequest(BaseModel):
    recipe_index: int = 0
    ingredients: List[str]


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


class WebRecipeManagerTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="recipe_manager", description="Manages recipe steps for web sessions"
        )

    def get_current_step(self, tool_context: ToolContext) -> dict:
        recipe_steps = tool_context.state.get("recipe_steps", {})
        current_index = tool_context.state.get("step_index", 0)

        if not recipe_steps:
            return {"step": "No recipe loaded", "step_number": 0, "is_complete": True}

        step_keys = sorted([int(k) for k in recipe_steps.keys()])

        if current_index >= len(step_keys):
            tool_context.state["recipe_completed"] = True
            return {
                "step": COMPLETION_PHRASE,
                "step_number": "complete",
                "is_complete": True,
            }

        current_step_key = str(step_keys[current_index])
        current_step_text = recipe_steps[current_step_key]

        tool_context.state["current_step_text"] = current_step_text
        tool_context.state["current_step_number"] = current_index + 1

        return {
            "step": current_step_text,
            "step_number": current_index + 1,
            "is_complete": False,
        }

    def advance_step(self, tool_context: ToolContext) -> dict:
        current_index = tool_context.state.get("step_index", 0)
        recipe_steps = tool_context.state.get("recipe_steps", {})
        step_keys = sorted([int(k) for k in recipe_steps.keys()])

        new_index = current_index + 1
        tool_context.state["step_index"] = new_index

        if new_index >= len(step_keys):
            tool_context.state["recipe_completed"] = True

        return {"status": "success", "message": f"Advanced to step {new_index + 1}"}


def wait_for_user_confirmation(tool_context: ToolContext) -> dict:
    return {"status": "waiting", "message": "Waiting for user input"}


def exit_loop(tool_context: ToolContext):
    tool_context.state["recipe_completed"] = True
    return {"status": "success", "message": "Recipe completed"}


recipe_manager_tool = WebRecipeManagerTool()

sous_chef_agent = Agent(
    name="WebSousChefAgent",
    model=MODEL,
    tools=[
        recipe_manager_tool.get_current_step,
        recipe_manager_tool.advance_step,
        parse_timer_duration,
        web_timer_tool,
        set_custom_timer,
        wait_for_user_confirmation,
        exit_loop,
    ],
    instruction="""You are a friendly Sous Chef helping users cook step by step through a web interface.

WORKFLOW:
1. First interaction: Greet, get_current_step, present step, wait_for_user_confirmation
2. User says 'next': advance_step, get_current_step, present step, handle timers if needed
3. Timer handling: parse_timer_duration → web_timer_tool
4. Completion: get_current_step returns completion phrase → exit_loop

TIMER WORKFLOW:
- Parse timer duration with parse_timer_duration
- Say: "I'll start a [duration] timer when ready. Type 'start' to begin, or different duration."
- User "start": Call web_timer_tool immediately
- Custom duration: Call set_custom_timer, wait for "start"

Keep responses encouraging and concise.""",
)


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
    return await smart_recipe_search_handler(payload.ingredients)


@app.post("/cooking/start")
async def start_cooking_session(request: StartCookingRequest) -> CookingResponse:
    try:
        recipe_response = await smart_recipe_search_handler(request.ingredients)

        if (
            not recipe_response.recipes
            or len(recipe_response.recipes) <= request.recipe_index
        ):
            raise HTTPException(status_code=404, detail="Recipe not found")

        selected_recipe = recipe_response.recipes[request.recipe_index]
        sous_chef_recipe = {
            "name": selected_recipe.sous_chef_format.name,
            "steps": selected_recipe.sous_chef_format.steps,
        }

        session_id = str(uuid.uuid4())
        initial_state = {
            "step_index": 0,
            "recipe_completed": False,
            "recipe_name": sous_chef_recipe["name"],
            "recipe_steps": sous_chef_recipe["steps"],
            "timer_active": False,
        }

        session = await recipe_memory_service.get_session_service().create_session(
            app_name=APP_NAME,
            user_id="web_user",
            session_id=session_id,
            state=initial_state,
        )

        runner = Runner(
            agent=sous_chef_agent,
            session_service=recipe_memory_service.get_session_service(),
            app_name=APP_NAME,
        )
        active_runners[session_id] = runner

        greeting_content = Content(
            parts=[Part(text="Hello, let's start cooking!")], role="user"
        )

        response_text = ""
        waiting_for_user = False

        async for event in runner.run_async(
            user_id="web_user", session_id=session_id, new_message=greeting_content
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text
                    elif (
                        part.function_call
                        and part.function_call.name == "wait_for_user_confirmation"
                    ):
                        waiting_for_user = True

            if event.is_final_response():
                break

        updated_session = await recipe_memory_service.get_session_service().get_session(
            app_name=APP_NAME, user_id="web_user", session_id=session_id
        )

        timer_info = get_timer_info(updated_session.state)

        return CookingResponse(
            session_id=session_id,
            message=response_text,
            waiting_for_user=waiting_for_user,
            timer_info=timer_info,
            recipe_completed=updated_session.state.get("recipe_completed", False),
        )

    except Exception as e:
        logger.error(f"Error starting cooking session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cooking/interact")
async def cooking_interaction(request: CookingInteraction) -> CookingResponse:
    try:
        runner = active_runners.get(request.session_id)
        if not runner:
            raise HTTPException(status_code=404, detail="Cooking session not found")

        # Check timer completion first
        session = await recipe_memory_service.get_session_service().get_session(
            app_name=APP_NAME, user_id="web_user", session_id=request.session_id
        )

        timer_completion_msg = check_timer_completion(session.state)

        user_content = Content(parts=[Part(text=request.message)], role="user")

        response_text = ""
        waiting_for_user = False

        async for event in runner.run_async(
            user_id="web_user", session_id=request.session_id, new_message=user_content
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text
                    elif (
                        part.function_call
                        and part.function_call.name == "wait_for_user_confirmation"
                    ):
                        waiting_for_user = True

            if event.is_final_response():
                break

        updated_session = await recipe_memory_service.get_session_service().get_session(
            app_name=APP_NAME, user_id="web_user", session_id=request.session_id
        )

        timer_info = get_timer_info(updated_session.state)
        recipe_completed = updated_session.state.get("recipe_completed", False)

        # Prepend timer completion message
        if timer_completion_msg:
            response_text = timer_completion_msg + "\n\n" + response_text

        if recipe_completed and request.session_id in active_runners:
            await recipe_memory_service.add_session_to_memory(updated_session)
            del active_runners[request.session_id]

        return CookingResponse(
            session_id=request.session_id,
            message=response_text,
            waiting_for_user=waiting_for_user,
            timer_info=timer_info,
            recipe_completed=recipe_completed,
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
            "recipe_completed": session.state.get("recipe_completed", False),
        }

    except Exception as e:
        logger.error(f"Error getting session status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cooking/{session_id}/timer")
async def get_timer_status(session_id: str):
    """Get current timer status for a session"""
    try:
        session = await recipe_memory_service.get_session_service().get_session(
            app_name=APP_NAME, user_id="web_user", session_id=session_id
        )

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        timer_info = get_timer_info(session.state)
        timer_completion_msg = check_timer_completion(session.state)

        # Save any state changes (like timer completion notification)
        if timer_completion_msg:
            await recipe_memory_service.get_session_service().update_session_state(
                app_name=APP_NAME,
                user_id="web_user",
                session_id=session_id,
                state=session.state,
            )

        return {
            "session_id": session_id,
            "timer_info": timer_info,
            "completion_message": timer_completion_msg,
        }

    except Exception as e:
        logger.error(f"Error getting timer status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/cooking/{session_id}")
async def end_cooking_session(session_id: str):
    """End a cooking session"""
    try:
        if session_id in active_runners:
            del active_runners[session_id]

        return {"message": "Cooking session ended", "session_id": session_id}

    except Exception as e:
        logger.error(f"Error ending session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

