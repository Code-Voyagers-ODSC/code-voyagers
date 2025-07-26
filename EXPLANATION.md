# Technical Explanation

## 1. Agent Workflow

1. **Receive user input**  
   Users upload a food photo or enter ingredients manually via the frontend.

2. **Plan sub-tasks**  
   The planner routes tasks to the appropriate agent:  
   - **Image input** → `Vision Agent`  
   - **Manual text input** → `Suggester Agent`  
   - **Cooking session** → `Sous Chef Agent`  

3. **Call tools or APIs as needed**  
   - Vision detection → Gemini Flash API  
   - Recipe search → DuckDuckGo Tool  
   - Cooking mode → Timer Tool and step formatter  

4. **Summarize and return final output**  
   Each agent formats and sends a structured response to the frontend: detected ingredients, recipe results, or current cooking step.

---

## 2. Key Modules

- **Planner** (`main.py`)  
  Routes incoming requests to the correct agent based on input type: image upload, text ingredients, or session command (e.g., "start", "next").

- **Executor** (`suggester_agent.py`, `ingredient_vision_agent.py`, `sous_chef_agent.py`)  
  Uses Google ADK to define each agent’s logic. Each agent calls Gemini models for reasoning and executes relevant tools.

- **Memory Store** (`cooking_session` in `sous_chef_agent.py`)  
  Temporarily stores per-session data:
  - Current recipe and cooking step  
  - Active timers  
  - Ingredient list  

---

## 3. Tool Integration

- **Search Tool** (`search_tool.py`)  
  - `search(query)` function uses DuckDuckGo to find web recipes.

- **Timer Tool** (`timer_tool.py`)  
  - Automatically extracts and runs countdown timers from recipe steps.

- **Gemini APIs**   
  - Gemini Flash: Recipe parsing, summarization, response formatting, and Image-based ingredient detection 

---

## 4. Observability & Testing

 

---

## 5. Known Limitations

- **No persistent memory yet** — all session data is cleared on restart.  
- **Vision edge cases** — cluttered images or poor lighting may reduce detection accuracy.  
- **API latency** — long-running calls to Gemini or web search may slow down response time during peak usage.
