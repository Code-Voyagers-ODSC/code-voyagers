# agents/ingredient_vision_agent.py

import io
import json
import os
import re
import sys
from typing import List

import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image
from pyprojroot.here import here

# Add project root to path for imports
project_root = here()
sys.path.insert(0, str(project_root))

# Load your API key from .env
load_dotenv(dotenv_path=here(".env"))
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


class IngredientVisionAgent:
    def __init__(self):
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    def load_image(self, path: str) -> Image.Image:
        """Load image from disk"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Image not found at {path}")
        return Image.open(path)

    def load_image_from_bytes(self, image_bytes: bytes) -> Image.Image:
        """Load image from bytes"""
        return Image.open(io.BytesIO(image_bytes))

    def classify_image(self, image: Image.Image) -> str:
        """Ask Gemini to classify ingredients in the image"""
        prompt = (
            "Look at the image and detect all visible food items. "
            "Respond ONLY with a JSON list of strings like: "
            '["chicken", "rice", "vegetables"]'
        )

        response = self.model.generate_content([prompt, image])
        return response.text

    def extract_json(self, text: str) -> str:
        """Clean the markdown wrapping from the Gemini output"""
        text = text.strip()
        if text.startswith("```json"):
            text = text[len("```json") :].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
        return match.group(0) if match else None

    def detect_ingredients_from_path(self, image_path: str) -> List[str]:
        """Detect ingredients from image file path"""
        try:
            image = self.load_image(image_path)
            result = self.classify_image(image)

            json_str = self.extract_json(result)
            if not json_str:
                raise ValueError(f"Could not extract JSON from model output: {result}")

            ingredients = json.loads(json_str)
            if not isinstance(ingredients, list):
                raise ValueError("Expected a list of ingredients")

            return ingredients

        except Exception as e:
            raise ValueError(f"Error detecting ingredients: {str(e)}")

    def detect_ingredients_from_bytes(self, image_bytes: bytes) -> List[str]:
        """Detect ingredients from image bytes"""
        try:
            image = self.load_image_from_bytes(image_bytes)
            result = self.classify_image(image)

            json_str = self.extract_json(result)
            if not json_str:
                raise ValueError(f"Could not extract JSON from model output: {result}")

            ingredients = json.loads(json_str)
            if not isinstance(ingredients, list):
                raise ValueError("Expected a list of ingredients")

            return ingredients

        except Exception as e:
            raise ValueError(f"Error detecting ingredients: {str(e)}")


# Global instance for use in main.py
ingredient_vision_agent = IngredientVisionAgent()


# Convenience functions for backward compatibility
def detect_ingredients_from_path(image_path: str) -> List[str]:
    return ingredient_vision_agent.detect_ingredients_from_path(image_path)


def detect_ingredients_from_bytes(image_bytes: bytes) -> List[str]:
    return ingredient_vision_agent.detect_ingredients_from_bytes(image_bytes)


if __name__ == "__main__":
    from loguru import logger

    # Test the agent
    image_path = here("images/fruit5.jpg")
    try:
        ingredients = detect_ingredients_from_path(image_path)
        logger.info(f"Detected ingredients: {ingredients}")

    except Exception as e:
        logger.error(f"Error: {e}")
