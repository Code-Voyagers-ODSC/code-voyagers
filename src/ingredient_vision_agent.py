import google.generativeai as genai
import json
from PIL import Image
import os
import re
from dotenv import load_dotenv

# Load your API key from .env
load_dotenv(dotenv_path="src/.env")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Load image from disk
def load_image(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Image not found at {path}")
    return Image.open(path)

# Ask Gemini to classify the object in the image
def classify_image(image):
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content([
        "Classify the object in this image. Is it a fruit or vegetable? Name it specifically. Respond ONLY in JSON with keys: 'type' and 'name'.",
        image
    ])
    return response.text

# Clean the markdown wrapping from the Gemini output
def extract_json(text):
    text = text.strip()
    if text.startswith("```json"):
        text = text[len("```json"):].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    match = re.search(r'{[\s\S]*}', text)
    return match.group(0) if match else None

if __name__ == "__main__":
    image_path = "images/fruit.jpg"
    image = load_image(image_path)
    result = classify_image(image)

    json_str = extract_json(result)
    if not json_str:
        print("Could not extract JSON from model output:")
        print(result)
    else:
        try:
            parsed = json.loads(json_str)
            print(json.dumps(parsed, indent=2))
            
            # Save to output.json
            with open("output.json", "w") as f:
                json.dump(parsed, f, indent=2)
                print("\n✅ JSON saved to output.json")

        except json.JSONDecodeError:
            print("Failed to parse extracted JSON:")
            print(json_str)