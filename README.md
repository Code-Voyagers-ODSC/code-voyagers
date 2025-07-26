# Super Spoon - Your Intelligent Sous Chef Agent

An AI-powered recipe assistant that finds recipes based on your ingredients and provides step-by-step cooking guidance. Features ingredient detection from photos using Google Gemini Vision and intelligent recipe recommendations.

## ✨ Features

- 🔍 **Smart Recipe Search**: Uses Google's Gemini AI to find recipes matching your ingredients
- 🖼️ **Ingredient Vision Agent**: Upload food photos to auto-detect ingredients via Google Gemini Vision model
- 👨🍳 **Interactive Cooking Mode**: Step-by-step guidance through each recipe
- ⏰ **Built-in Timers**: Automatic timer detection and countdown for cooking steps
- 🛡️ **Food Safety Tips**: Includes temperature guidelines and safe handling practices
- 📱 **Responsive Design**: Works on desktop and mobile devices

## Sample Screenshots

> Click to enlarge

<div style="display: flex; flex-wrap: wrap; gap: 1rem;">

<!-- Replace these paths and alt‑text with your real screenshots -->
<img src="images/Home Page.png" alt="Super Spoon Home Screen" width="250" />
<img src="images/Detail Page.png" alt="Recipe Search Results" width="250" />
<img src="images/List Page.png" alt="Interactive Cooking Mode" width="250" />
<img src="images/Timer Page.png" alt="Built-in Timer Popup" width="250" />

</div>
 

## 🧑‍🍳 Using the Agent

### Basic Recipe Search
1. Open `http://localhost:8081` in your browser
2. Enter ingredients manually or upload a food photo
3. Click "Search Recipes" to get AI-powered suggestions
4. Select a recipe to start interactive cooking mode
5. Press the "Next" button to move to the next step

## 📋 Prerequisites

- **Python**: 3.8 or higher
- **Node.js**: 16.0 or higher
- **uv**: Modern Python package manager (recommended) - [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
- **Google Gemini API Key** - Get one from [Google AI Studio](https://makersuite.google.com/app/apikey)

## 🚀 Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/Code-Voyagers-ODSC/code-voyagers.git
cd code-voyagers
```

### 2. Backend Setup

#### Install Dependencies

**Option A: Using uv (Recommended)**
```bash
# Install uv package manager if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies automatically
uv sync

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate     # Windows
```

**Option B: Using pip**
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate   # macOS/Linux
# or
venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt
```

#### Configure API Key
```bash
# Create .env file with your API key
echo "GEMINI_API_KEY=your-api-key-here" > .env
```

### 3. Run the Agent

#### Start Backend (Primary Method)
```bash
cd src
python main.py
```

**Alternative (if main.py doesn't work directly):**
```bash
cd src
uvicorn main:app --reload --port 8000
```

The backend will be available at `http://localhost:8000`

#### Start Frontend
```bash
# In a new terminal
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:8081`

## 📦 Dependencies

### Core Backend Dependencies
- **FastAPI** - Web framework for the API
- **Google Generative AI** - Gemini models for recipe suggestions and vision
- **Pillow** - Image processing for ingredient detection
- **uvicorn** - ASGI server for running the API

### Frontend Dependencies
- **Next.js** - React framework for the UI
- **React** - Frontend library
- **TailwindCSS** - Styling

## 🛠️ Project Structure

```
code-voyagers/
├── src/
│   ├── main.py                     # FastAPI app entry point (run this!)
│   ├── agents/
│   │   ├── suggester_agent.py      # Recipe AI agent
│   │   ├── ingredient_vision_agent.py  # Photo ingredient detection
│   │   └── sous_chef_agent.py      # Cooking guidance agent
│   └── tools/
│       ├── search_tool.py          # Recipe search functionality
│       └── timer_tool.py           # Cooking timers
├── frontend/                       # Next.js React app
├── requirements.txt                # Python dependencies
├── pyproject.toml                 # uv configuration
└── .env                           # API keys (create this)
```

## 🔧 Troubleshooting

**Backend won't start:**
- Ensure Python 3.8+ is installed: `python --version`
- Check virtual environment is activated (see `(.venv)` or `(venv)` in terminal)
- Verify API key is set: `cat .env` (should show your Gemini API key)

**"ModuleNotFoundError":**
- Make sure you're in the activated virtual environment
- Try: `pip install -r requirements.txt` (even if using uv)

**Frontend issues:**
- Confirm backend is running on port 8000
- Check Node.js version: `node --version` (need 16+)
- Try: `npm install --force` if dependency issues

**API errors:**
- Verify your Gemini API key is valid at [Google AI Studio](https://aistudio.google.com/app/apikey)
- Check API quotas/limits in Google Cloud Console

**Port already in use:**
- Backend: Change port in `main.py` or use `python main.py --port 8001`
- Frontend: Use `npm run dev -- --port 3001`

---
