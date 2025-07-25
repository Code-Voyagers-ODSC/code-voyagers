from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

from agents.suggester_agent import smart_recipe_search_handler

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8082"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class IngredientList(BaseModel):
    ingredients: List[str]

@app.post("/agent/smart-search")
async def smart_recipe_search(payload: IngredientList):
    return await smart_recipe_search_handler(payload.ingredients)

@app.get("/")
def home():
    return {"message": "Gemini-powered backend is up and running!"}
