import google.generativeai as genai
import os
import json
import re
from dotenv import load_dotenv
from tools.search_tool import web_search_recipes_tool

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

async def smart_recipe_search_handler(ingredients, user_preferences=None):
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

    # Build personalization context
    personalization_context = _build_personalization_context(user_preferences, ingredients)

    full_prompt = (
        "You are a cooking assistant. From the search results, select the 3-4 best recipes that match the requested ingredients. "
        "Be flexible - if a recipe contains most of the ingredients or similar ingredients, include it.\n\n"
        f"{personalization_context}\n\n"
        "IMPORTANT:\n"
        "• Even if the search results don't perfectly match all ingredients, extract what you can.\n"
        "• For example, if searching for 'chicken pasta garlic' and you find 'garlic chicken' recipes, adapt them.\n"
        "• Use the user's preferences to prioritize and recommend recipes they're more likely to enjoy.\n"
        "• If you can adapt a recipe to better match their preferences, mention it in the description.\n\n"
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
        "    \"food_safety_summary\": \"...\",\n"
        "    \"personalization_note\": \"Brief note about why this matches user preferences (if applicable)\"\n"
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
            
            # Add user preference context to response
            response_data = {
                "recipes": parsed_json,
                "personalization": {
                    "total_liked_recipes": len(user_preferences.get("liked_recipes", [])) if user_preferences else 0,
                    "preferences_used": bool(user_preferences and user_preferences.get("liked_recipes"))
                }
            }
            
            return response_data
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

def _build_personalization_context(user_preferences, current_ingredients):
    """Build context about user preferences for the AI prompt"""
    if not user_preferences or not user_preferences.get("liked_recipes"):
        return "USER PREFERENCES: No previous recipe preferences available - treat as new user."
    
    liked_recipes = user_preferences["liked_recipes"]
    patterns = user_preferences["preference_patterns"]
    
    context_parts = ["USER PREFERENCES (use this to personalize recommendations):"]
    
    # Add info about liked recipes count
    context_parts.append(f"• User has liked {len(liked_recipes)} recipes previously")
    
    # Add favorite cuisines
    if patterns.get("cuisines"):
        top_cuisines = sorted(patterns["cuisines"].items(), key=lambda x: x[1], reverse=True)[:3]
        cuisine_list = [f"{cuisine} ({count}x)" for cuisine, count in top_cuisines]
        context_parts.append(f"• Preferred cuisines: {', '.join(cuisine_list)}")
    
    # Add preferred difficulty levels
    if patterns.get("difficulty_levels"):
        top_difficulties = sorted(patterns["difficulty_levels"].items(), key=lambda x: x[1], reverse=True)[:2]
        diff_list = [f"{diff} ({count}x)" for diff, count in top_difficulties]
        context_parts.append(f"• Preferred difficulty: {', '.join(diff_list)}")
    
    # Add preferred cooking times
    if patterns.get("cooking_times"):
        top_times = sorted(patterns["cooking_times"].items(), key=lambda x: x[1], reverse=True)[:2]
        time_list = [f"{time} ({count}x)" for time, count in top_times]
        context_parts.append(f"• Preferred cooking times: {', '.join(time_list)}")
    
    # Add frequently used ingredients
    if patterns.get("ingredients"):
        # Filter out current ingredients to avoid redundancy
        current_ingredients_lower = [ing.lower() for ing in current_ingredients]
        filtered_ingredients = {
            ing: count for ing, count in patterns["ingredients"].items() 
            if ing not in current_ingredients_lower and count > 1
        }
        
        if filtered_ingredients:
            top_ingredients = sorted(filtered_ingredients.items(), key=lambda x: x[1], reverse=True)[:5]
            ing_list = [f"{ing} ({count}x)" for ing, count in top_ingredients]
            context_parts.append(f"• Frequently enjoyed ingredients: {', '.join(ing_list)}")
    
    # Add recent liked recipes for context
    if len(liked_recipes) > 0:
        recent_recipes = liked_recipes[-3:]  # Last 3 liked recipes
        recent_titles = [recipe["title"] for recipe in recent_recipes]
        context_parts.append(f"• Recently liked: {', '.join(recent_titles)}")
    
    return "\n".join(context_parts)

def clean_json_response(response_text):
    response_text = re.sub(r'```', '', response_text)  # Fixed: closed string and added replacement argument
    response_text = re.sub(r'```\s*', '', response_text)

    start_idx = response_text.find('[')
    end_idx = response_text.rfind(']')

    if start_idx == -1 or end_idx == -1:
        raise ValueError("No valid JSON array found in response")

    json_text = response_text[start_idx:end_idx + 1]
    json_text = re.sub(r',\s*}', '}', json_text)
    json_text = re.sub(r',\s*]', ']', json_text)
    
    return json_text
