import React, { useState, useEffect } from 'react';
import { Upload, Search, Play, Clock, Plus, X, ChefHat } from 'lucide-react';

const API_BASE = 'http://localhost:8000';

export default function CookingAssistantUI() {
  const [ingredients, setIngredients] = useState([]);
  const [recipes, setRecipes] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [cookingMessage, setCookingMessage] = useState('');
  const [waitingForUser, setWaitingForUser] = useState(false);
  const [timerInfo, setTimerInfo] = useState(null);
  const [newIngredient, setNewIngredient] = useState('');
  const [loading, setLoading] = useState(false);

  // Fetch ingredients on load
  useEffect(() => {
    fetchIngredients();
  }, []);

  const fetchIngredients = async () => {
    try {
      const response = await fetch(`${API_BASE}/ingredients`);
      const data = await response.json();
      setIngredients(data.ingredients);
    } catch (error) {
      console.error('Error fetching ingredients:', error);
    }
  };

  const handleImageUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_BASE}/agent/detect-ingredients`, {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      setIngredients(data.all_ingredients);
    } catch (error) {
      console.error('Error detecting ingredients:', error);
    } finally {
      setLoading(false);
    }
  };

  const addIngredient = async () => {
    if (!newIngredient.trim()) return;

    try {
      const response = await fetch(`${API_BASE}/ingredients`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ingredients: [newIngredient.trim()] }),
      });
      const data = await response.json();
      setIngredients(data.ingredients);
      setNewIngredient('');
    } catch (error) {
      console.error('Error adding ingredient:', error);
    }
  };

  const removeIngredient = async (ingredientToRemove) => {
    const updatedIngredients = ingredients.filter(ing => ing !== ingredientToRemove);
    try {
      const response = await fetch(`${API_BASE}/ingredients`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ingredients: updatedIngredients }),
      });
      const data = await response.json();
      setIngredients(data.ingredients);
    } catch (error) {
      console.error('Error removing ingredient:', error);
    }
  };

  const searchRecipes = async () => {
    if (ingredients.length === 0) return;

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/agent/smart-search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ingredients: [] }), // Will use stored ingredients
      });
      const data = await response.json();
      setRecipes(data.recipes);
    } catch (error) {
      console.error('Error searching recipes:', error);
    } finally {
      setLoading(false);
    }
  };

  const startCooking = async (recipeId) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/cooking/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: recipeId }),
      });
      const data = await response.json();
      setCurrentSession(data.session_id);
      setCookingMessage(data.message);
      setWaitingForUser(data.waiting_for_user);
      setTimerInfo(data.timer_info);
    } catch (error) {
      console.error('Error starting cooking:', error);
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async (message) => {
    if (!currentSession) return;

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/cooking/interact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSession, message }),
      });
      const data = await response.json();
      setCookingMessage(data.message);
      setWaitingForUser(data.waiting_for_user);
      setTimerInfo(data.timer_info);
      
      if (data.recipe_completed) {
        setCurrentSession(null);
      }
    } catch (error) {
      console.error('Error sending message:', error);
    } finally {
      setLoading(false);
    }
  };

  const clearAll = async () => {
    try {
      await fetch(`${API_BASE}/ingredients`, { method: 'DELETE' });
      setIngredients([]);
      setRecipes([]);
      setCurrentSession(null);
      setCookingMessage('');
    } catch (error) {
      console.error('Error clearing data:', error);
    }
  };

  if (currentSession) {
    return (
      <div className="max-w-4xl mx-auto p-6 bg-white min-h-screen">
        <div className="bg-green-50 border-l-4 border-green-400 p-6 rounded-lg">
          <div className="flex items-center mb-4">
            <ChefHat className="w-6 h-6 text-green-600 mr-2" />
            <h2 className="text-xl font-semibold text-green-800">Cooking Session</h2>
          </div>
          
          <div className="bg-white p-4 rounded-lg shadow-sm mb-4">
            <p className="text-gray-800 whitespace-pre-wrap">{cookingMessage}</p>
          </div>

          {timerInfo?.active && (
            <div className="bg-orange-100 border border-orange-300 p-3 rounded-lg mb-4 flex items-center">
              <Clock className="w-5 h-5 text-orange-600 mr-2" />
              <span className="text-orange-800">
                Timer: {timerInfo.remaining_seconds}s remaining
              </span>
            </div>
          )}

          <div className="flex gap-2">
            {waitingForUser && (
              <button
                onClick={() => sendMessage('next')}
                disabled={loading}
                className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50"
              >
                Next Step
              </button>
            )}
            <button
              onClick={() => sendMessage('start')}
              disabled={loading}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              Start Timer
            </button>
            <button
              onClick={() => setCurrentSession(null)}
              className="bg-gray-600 text-white px-4 py-2 rounded-lg hover:bg-gray-700"
            >
              End Session
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6 bg-gray-50 min-h-screen">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-800 mb-2">🍳 Cooking Assistant</h1>
        <p className="text-gray-600">Upload images, detect ingredients, search recipes, and cook!</p>
      </div>

      {/* Image Upload */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center">
          <Upload className="w-5 h-5 mr-2" />
          Upload Food Image
        </h2>
        <input
          type="file"
          accept="image/*"
          onChange={handleImageUpload}
          className="w-full p-3 border-2 border-dashed border-gray-300 rounded-lg hover:border-gray-400"
        />
      </div>

      {/* Ingredients */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Ingredients ({ingredients.length})</h2>
          <button
            onClick={clearAll}
            className="text-red-600 hover:text-red-800 text-sm"
          >
            Clear All
          </button>
        </div>
        
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={newIngredient}
            onChange={(e) => setNewIngredient(e.target.value)}
            placeholder="Add ingredient..."
            className="flex-1 p-2 border border-gray-300 rounded-lg"
            onKeyPress={(e) => e.key === 'Enter' && addIngredient()}
          />
          <button
            onClick={addIngredient}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 flex items-center"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          {ingredients.map((ingredient, index) => (
            <span
              key={index}
              className="bg-green-100 text-green-800 px-3 py-1 rounded-full text-sm flex items-center"
            >
              {ingredient}
              <button
                onClick={() => removeIngredient(ingredient)}
                className="ml-2 text-green-600 hover:text-green-800"
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>

        {ingredients.length > 0 && (
          <button
            onClick={searchRecipes}
            disabled={loading}
            className="mt-4 bg-orange-600 text-white px-6 py-2 rounded-lg hover:bg-orange-700 disabled:opacity-50 flex items-center"
          >
            <Search className="w-4 h-4 mr-2" />
            {loading ? 'Searching...' : 'Search Recipes'}
          </button>
        )}
      </div>

      {/* Recipes */}
      {recipes.length > 0 && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold mb-4">Found Recipes ({recipes.length})</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {recipes.map((recipe) => (
              <div key={recipe.id} className="border border-gray-200 rounded-lg p-4">
                <h3 className="font-semibold text-lg mb-2">{recipe.summary.title}</h3>
                <div className="text-sm text-gray-600 space-y-1 mb-3">
                  <p>⏱️ {recipe.summary.estimated_time}</p>
                  <p>👥 {recipe.summary.serves}</p>
                  <p>📊 {recipe.summary.difficulty}</p>
                  <p>🍽️ {recipe.summary.cuisine_type}</p>
                </div>
                <p className="text-gray-700 text-sm mb-3">{recipe.summary.description}</p>
                <button
                  onClick={() => startCooking(recipe.id)}
                  disabled={loading}
                  className="w-full bg-green-600 text-white py-2 rounded-lg hover:bg-green-700 disabled:opacity-50 flex items-center justify-center"
                >
                  <Play className="w-4 h-4 mr-2" />
                  Start Cooking
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
          <div className="bg-white p-6 rounded-lg">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-2 text-gray-600">Processing...</p>
          </div>
        </div>
      )}
    </div>
  );
}