# AI Recipe Suggester with Interactive Cooking Guide

An intelligent recipe suggestion system that finds recipes based on your ingredients and provides step-by-step cooking guidance, plus an image-based ingredient detector for added convenience.

## Features

* 🔍 **Smart Recipe Search:** Uses Google's Gemini AI to find recipes matching your ingredients.
* 🖼️ **Ingredient Vision Agent:** Upload food photos to auto-detect ingredients via a Google Gemini Vision model.
* 👨‍🍳 **Interactive Cooking Mode:** Step-by-step guidance through each recipe.
* ⏰ **Built-in Timers:** Automatic timer detection and countdown for cooking steps.
* 🛡️ **Food Safety Tips:** Includes temperature guidelines and safe handling practices.
* 📱 **Responsive Design:** Works on desktop and mobile devices.

## Architecture

* **Backend:** FastAPI + Google ADK (Agent Development Kit)
* **Vision Agent:** Multimodal Google Gemini Pro Vision model for image-to-ingredient detection
* **Frontend:** Next.js / React
* **AI Models:** Google Gemini 2.5 Flash
* **Search:** DuckDuckGo for web recipe search

## Quick Start

### Prerequisites

* Python 3.8+
* Node.js 16+
* Google Gemini API key

### Backend Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-org/recipe-suggestor.git
   cd recipe-suggestor
   ```
2. **Create and activate a virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```
3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   pip install pillow google-generativeai
   ```
4. **Set up environment variables**

   ```bash
   echo "GEMINI_API_KEY=your-api-key-here" > .env
   ```
5. **Run the backend server**

   ```bash
   cd src
   uvicorn main:app --reload --port 8000
   ```

### Frontend Setup

1. **Navigate to frontend directory**

   ```bash
   cd ../frontend
   ```
2. **Install dependencies**

   ```bash
   npm install
   ```
3. **Run the development server**

   ```bash
   npm run dev
   ```
4. Visit **[http://localhost:8081](http://localhost:8081)** in your browser.

## Usage

1. Upload a food image or manually enter ingredients.
2. Click **Search Recipes** to find matching recipes.
3. Click a recipe to view details.
4. Click **Start Cooking** for interactive, step-by-step guidance.

## API Endpoints

### Search Recipes

```http
POST /agent/smart-search
Content-Type: application/json

{"ingredients": ["chicken","pasta","garlic"]}
```

### Detect Ingredients from Image

```http
POST /agent/detect-ingredients
Content-Type: multipart/form-data

FormData: file=<image file>

Response: {"ingredients": ["tomato","basil","mozzarella"]}
```

### Start Cooking Session

```http
POST /cooking/start
Content-Type: application/json

{
  "sous_chef_format": {
    "name": "Recipe Name",
    "steps": {"1":"First step","2":"Second step"}
  }
}
```

### Next Cooking Step

```http
POST /cooking/next
Content-Type: application/json

{"session_id":"<uuid>","command":"next"}
```

### Get Session Status

```http
GET /cooking/status/{session_id}
```

## Project Structure

```
CODE-VOYAGERS/

├── src/
│   ├── main.py
│   ├── agents/
│   │   ├── suggester_agent.py
│   │   ├── ingredient_vision_agent.py
│   │   └── sous_chef_agent.py
│   └── tools/
│       └── search_tool.py
│       └── timer_tool.py  
└── requirements.txt
└── README.md
```

## Key Features Explained

### Intelligent Recipe Matching

* Searches the web for recipes containing your ingredients.
* AI analyzes and structures the results into summaries and detailed steps.

### Ingredient Vision Agent

* Upload a photo of your ingredients or pantry.
* The vision agent (Gemini Pro Vision) detects visible food items.
* Returns a JSON list of ingredients to seed your search.

### Interactive Cooking Mode

* Guides you through each step of the recipe.
* Detects timer requirements automatically.
* Tracks progress with visual indicators and timers.

## Troubleshooting

* **Backend won't start**: Ensure Python 3.8+, dependencies installed, and `.env` contains `GEMINI_API_KEY`.
* **Vision endpoint errors**: Verify `pillow` and `google-generativeai` are installed and the key is valid.
* **Frontend issues**: Confirm backend is running on port 8000 and CORS settings are correct.

## Future Enhancements

* User accounts and saved recipes
* Shopping list generation
* Nutritional information
* Voice control for hands-free cooking
* Recipe rating and feedback
* Multi-language support

## Contributing

Contributions welcome! Please open issues or pull requests for bugs and enhancements.

## License

MIT License
