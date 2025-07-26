import os
import json
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.llms import GeminiVisionModel
from google.adk.runners import Runner
from google.adk.media import Image

# Step 1: Load environment
load_dotenv()

# Step 2: Define your vision agent
ingredient_vision_agent = Agent(
    name="ingredient_vision_agent",
    model=GeminiVisionModel(model="models/gemini-1.5-pro-vision"),
    system_instruction=(
        "You are a helpful cooking assistant. "
        "When shown an image of ingredients, analyze the image and respond with a clean, simple list "
        "of all recognizable fruits or vegetables only. Do not include utensils, containers, or background objects."
    ),
)

# Step 3: Load the image
image_path = "fruit.jpg"  # Replace with your actual file path
with open(image_path, "rb") as f:
    image = Image.from_bytes(f.read(), mime_type="image/jpeg")

# Step 4: Run the agent
runner = Runner()
response = runner.run(ingredient_vision_agent, image)

# Step 5: Save to JSON
ingredients_list = [item.strip("- ").strip() for item in response.text.split("\n") if item.strip()]
output_data = {"recognized_items": ingredients_list}

with open("recognized_fruits_veggies.json", "w") as f:
    json.dump(output_data, f, indent=2)

print("Saved to recognized_fruits_veggies.json")