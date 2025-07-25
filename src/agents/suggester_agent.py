import google.generativeai as genai
import os
import json
import re
from dotenv import load_dotenv
from tools.search_tool import web_search_recipes_tool

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

async def smart_recipe_search_handler(ingredients):
    print(f"\n=== New search request for ingredients: {ingredients} ===")
    
    search_results = web_search_recipes_tool(ingredients)
    print(f"Search returned {len(search_results)} results")

    if not search_results:
        return {
            "error": f"No recipes found for {', '.join(ingredients)}. Try different ingredients or fewer ingredients.",
            "suggestions": [
                "Try searching with just one or two main ingredients",
                "Use more common ingredient names",
                "Check spelling of ingredients"
            ]
        }

    for i, result in enumerate(search_results):
        print(f"\nResult {i+1}:")
        print(f"  Title: {result['title']}")
        print(f"  Link: {result['link']}")
        print(f"  Snippet: {result['snippet'][:100]}...")

    formatted = "\n\n".join(
        f"Title: {r['title']}\nLink: {r['link']}\nSnippet: {r['snippet']}"
        for r in search_results
    )

    full_prompt = (
        "You are a cooking assistant. From the search results, select the 3-4 best recipes that match the requested ingredients. "
        "Be flexible - if a recipe contains most of the ingredients or similar ingredients, include it.\n\n"
        "IMPORTANT:\n"
        "• Even if the search results don't perfectly match all ingredients, extract what you can.\n"
        "• For example, if searching for 'chicken pasta garlic' and you find 'garlic chicken' recipes, adapt them.\n\n"
        "Return ONLY a valid JSON array with no additional text or formatting.\n\n"
        "Each recipe must include the following structure:\n\n"
        "{\n"
        "  \"id\": \"recipe_1\",\n"
        "  \"summary\": {\n"
        "    \"title\": \"...\",\n"
        "    \"link\": \"...\",\n"
        "    \"description\": \"...\",\n"
        "    \"estimated_time\": \"...\",\n"
        "    \"difficulty\": \"...\",\n"
        "    \"cuisine_type\": \"...\",\n"
        "    \"serves\": \"...\",\n"
        "    \"food_safety_summary\": \"...\"\n"
        "  },\n"
        "  \"details\": {\n"
        "    \"ingredients\": [\"...\"],\n"
        "    \"equipment_needed\": [\"...\"],\n"
        "    \"prep_time\": \"...\",\n"
        "    \"cook_time\": \"...\",\n"
        "    \"method_overview\": \"...\",\n"
        "    \"key_techniques\": [\"...\"],\n"
        "    \"food_safety_details\": {\n"
        "      \"temperature_guidelines\": \"...\",\n"
        "      \"storage_instructions\": \"...\",\n"
        "      \"handling_tips\": \"...\"\n"
        "    },\n"
        "    \"dietary_info\": [\"...\"],\n"
        "    \"substitutions\": [\"...\"],\n"
        "    \"chef_tips\": [\"...\"],\n"
        "    \"serving_suggestions\": [\"...\"],\n"
        "    \"make_ahead_notes\": \"...\",\n"
        "    \"troubleshooting\": [\"...\"]\n"
        "  }\n"
        "}\n\n"
        f"Requested ingredients: {', '.join(ingredients)}\n\nSearch Results:\n{formatted}"
    )

    try:
        print("\nCalling Gemini to process results...")
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(full_prompt)

        raw_response = response.text.strip()
        print(f"\nGemini raw response length: {len(raw_response)} characters")

        cleaned_response = clean_json_response(raw_response)

        try:
            parsed_json = json.loads(cleaned_response)
            print(f"Successfully parsed {len(parsed_json)} recipes")
            return {"recipes": parsed_json}
        except json.JSONDecodeError as e:
            print(f"JSON validation failed: {e}")
            return {
                "error": "Failed to parse recipe data from Gemini",
                "debug_info": str(e),
                "raw_preview": raw_response[:200]
            }

    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return {"error": f"Failed to process recipes: {str(e)}"}

def clean_json_response(response_text):
    response_text = re.sub(r'```json\s*', '', response_text)
    response_text = re.sub(r'```\s*', '', response_text)

    start_idx = response_text.find('[')
    end_idx = response_text.rfind(']')

    if start_idx == -1 or end_idx == -1:
        raise ValueError("No valid JSON array found in response")

    json_text = response_text[start_idx:end_idx + 1]
    json_text = re.sub(r',\s*}', '}', json_text)
    json_text = re.sub(r',\s*]', ']', json_text)
    return json_text
