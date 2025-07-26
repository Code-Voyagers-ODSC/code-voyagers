from duckduckgo_search import DDGS
import re

def web_search_recipes_tool(ingredients: list[str]) -> list[dict]:
    # Try multiple search strategies
    search_queries = [
        f"recipe {' '.join(ingredients)}",  # "recipe chicken pasta garlic"
        f"{' '.join(ingredients)} recipe",   # "chicken pasta garlic recipe"
        f"easy {' '.join(ingredients)} recipe",  # Sometimes "easy" helps find more results
    ]
    
    all_recipes = []
    seen_urls = set()  # Track URLs to avoid duplicates
    
    for query in search_queries:
        print(f"Searching with query: {query}")
        
        try:
            with DDGS() as ddgs:
                results = ddgs.text(query, max_results=15)  # Increased from 10
                
                for r in results:
                    title = r.get("title", "")
                    link = r.get("href", "")
                    snippet = r.get("body", "")
                    
                    # Skip if we've seen this URL
                    if link in seen_urls:
                        continue
                    
                    # More flexible relevance filter
                    title_lower = title.lower()
                    snippet_lower = snippet.lower()
                    
                    # Check if it's likely a recipe (more flexible criteria)
                    is_recipe = any([
                        "recipe" in title_lower,
                        "recipe" in snippet_lower,
                        "how to make" in title_lower,
                        "how to cook" in title_lower,
                        any(word in title_lower for word in ["easy", "simple", "quick", "homemade"]),
                        # Check if key ingredients are mentioned
                        sum(1 for ing in ingredients if ing.lower() in title_lower + " " + snippet_lower) >= 2
                    ])
                    
                    # Also check it's not a video-only result or shopping link
                    is_excluded = any([
                        "youtube.com" in link.lower(),
                        "amazon.com" in link.lower(),
                        "shop" in link.lower(),
                        "buy" in title_lower,
                        "price" in title_lower
                    ])
                    
                    if is_recipe and not is_excluded and link and snippet:
                        all_recipes.append({
                            "title": title,
                            "link": link,
                            "snippet": snippet
                        })
                        seen_urls.add(link)
                        
                        print(f"  Found recipe: {title}")
                    
                    # Stop if we have enough unique recipes
                    if len(all_recipes) >= 8:  # Increased from 5
                        break
                
        except Exception as e:
            print(f"Error with search query '{query}': {e}")
            continue
        
        # If we have enough recipes, stop trying other queries
        if len(all_recipes) >= 5:
            break
    
    print(f"Total recipes found: {len(all_recipes)}")
    
    # If we still don't have any recipes, try a more general search
    if len(all_recipes) == 0:
        print("No recipes found with specific queries, trying general search...")
        general_query = f"dinner recipe with {ingredients[0]}"  # Focus on first ingredient
        
        try:
            with DDGS() as ddgs:
                results = ddgs.text(general_query, max_results=10)
                
                for r in results:
                    title = r.get("title", "")
                    link = r.get("href", "")
                    snippet = r.get("body", "")
                    
                    if link and snippet and "recipe" in (title + snippet).lower():
                        all_recipes.append({
                            "title": title,
                            "link": link,
                            "snippet": snippet
                        })
                        
                        if len(all_recipes) >= 3:
                            break
                            
        except Exception as e:
            print(f"Error with general search: {e}")
    
    return all_recipes