# src/agents/ingredient_vision_agent.py

import io
import json
import os
import re
from typing import List

import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image
from pyprojroot.here import here

# bootstrap
load_dotenv(dotenv_path=here(".env"))
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY not set in .env")
genai.configure(api_key=api_key)

class IngredientVisionAgent:
    def __init__(self, model_name: str = "gemini-2.0-flash"):
        # “gemini-pro-vision” is the multimodal‑capable variant
        self.model = genai.GenerativeModel(model_name)

    def _prompt(self) -> str:
        return (
            "Look at the image and detect all visible food items. "
            "Respond **only** with a JSON array of strings, e.g.:\n"
            '["chicken", "rice", "tomatoes"]'
        )

    def _serialize_image(self, img: Image.Image) -> dict:
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return {
            "mime_type": "image/jpeg",
            "data": buf.getvalue()
        }

    def extract_json(self, text: str) -> str:
        # strip ``` fences and grab the first JSON array
        t = text.strip()
        t = re.sub(r"^```json\s*", "", t)
        t = re.sub(r"```$", "", t)
        m = re.search(r"(\[.*\])", t, re.DOTALL)
        return m.group(1) if m else None

    def detect_ingredients_from_path(self, path: str) -> List[str]:
        img = Image.open(path).convert("RGB")
        return self._run(img)

    def detect_ingredients_from_bytes(self, image_bytes: bytes) -> List[str]:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return self._run(img)

    def _run(self, img: Image.Image) -> List[str]:
        prompt = self._prompt()
        image_part = self._serialize_image(img)

        # Call generate_content _positionally_ with [prompt, image_part]
        resp = self.model.generate_content([prompt, image_part])

        json_str = self.extract_json(resp.text)
        if not json_str:
            raise ValueError(f"Could not parse JSON from model output:\n{resp.text}")

        parsed = json.loads(json_str)
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON **list** of ingredient names")
        return parsed

# expose module‑level helpers
ingredient_vision_agent = IngredientVisionAgent()

def detect_ingredients_from_bytes(image_bytes: bytes) -> List[str]:
    return ingredient_vision_agent.detect_ingredients_from_bytes(image_bytes)

def detect_ingredients_from_path(path: str) -> List[str]:
    return ingredient_vision_agent.detect_ingredients_from_path(path)
