# agent that detects ingredients from images

import os
from google.adk.agents import Agent
from google.adk.llms import GeminiVisionModel
from dotenv import load_dotenv

# Load your .env file so the GOOGLE_API_KEY is available
load_dotenv()

# Create an agent that uses the Gemini Vision model
ingredient_vision_agent = Agent(
    name="ingredient_vision_agent",
    model=GeminiVisionModel(model="models/gemini-1.5-pro-vision"),
    system_instruction=(
        "You are a helpful cooking assistant. "
        "When shown an image of ingredients, analyze the image and respond with a clean, simple list "
        "of all recognizable ingredients. Only list food items — no containers, utensils, or background details."
    ),
)