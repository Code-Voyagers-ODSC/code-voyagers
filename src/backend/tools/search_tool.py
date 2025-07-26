# src/backend/tools/search_tool.py

from duckduckgo_search import DDGS

def web_search_recipes_tool(ingredients: list[str]) -> list[dict]:
    # Try multiple search strategies
    search_queries = [
        f"recipe {' '.join(ingredients)}",
        f"{' '.join(ingredients)} recipe",
        f"easy {' '.join(ingredients)} recipe",
    ]
    
    all_recipes = []
    seen_urls = set()
    
    for query in search_queries:
        print(f"Searching with query: {query}")
        try:
            with DDGS() as ddgs:
                results = ddgs.text(query, max_results=15)
                for r in results:
                    title = r.get("title", "")
                    link = r.get("href", "")
                    snippet = r.get("body", "")
                    if link in seen_urls:
                        continue
                    
                    title_lower = title.lower()
                    snippet_lower = snippet.lower()
                    is_recipe = any([
                        "recipe" in title_lower,
                        "recipe" in snippet_lower,
                        "how to make" in title_lower,
                        "how to cook" in title_lower,
                        any(w in title_lower for w in ["easy", "simple", "quick", "homemade"]),
                        sum(1 for ing in ingredients if ing.lower() in title_lower + " " + snippet_lower) >= 2
                    ])
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
                    if len(all_recipes) >= 8:
                        break
        except Exception as e:
            print(f"Error with search query '{query}': {e}")
            continue
        if len(all_recipes) >= 5:
            break

    if not all_recipes:
        print("No recipes found with specific queries, trying general search...")
        general_query = f"dinner recipe with {ingredients[0]}"
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
