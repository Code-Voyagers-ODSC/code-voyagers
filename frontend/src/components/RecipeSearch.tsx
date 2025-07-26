import { useState, useEffect } from "react";
import { Search, ChefHat, Clock, Users, Star, ArrowLeft, ExternalLink, Shield, Lightbulb, Sparkles, Loader2, AlertTriangle, Utensils, Menu, Upload, X, Timer, PlayCircle, SkipForward } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface Recipe {
  summary: {
    title: string;
    description: string;
    link: string;
    serves?: string;
    difficulty?: string;
    food_safety_summary?: string;
  };
  details: {
    ingredients: string[];
    prep_time?: string;
    cook_time?: string;
    method_overview?: string;
    key_techniques?: string[];
    food_safety_details?: {
      temperature_guidelines?: string;
      storage_instructions?: string;
      handling_tips?: string;
    };
    chef_tips?: string[];
  };
  sous_chef_format?: {
    steps: Record<string, string>;
  };
}

interface CookingSession {
  session_id: string;
  recipe_name: string;
  current_step: number;
  total_steps: number;
  step_text: string;
  has_timer: boolean;
}

interface CurrentStep {
  number: number;
  text: string;
  hasTimer: boolean;
  total: number;
}

const RecipeSearch = () => {
  // Combined ingredient state
  const [ingredients, setIngredients] = useState<string[]>([]);
  const [fileError, setFileError] = useState("");
  const [inputValue, setInputValue] = useState("");

  // Existing state
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedRecipe, setSelectedRecipe] = useState<Recipe | null>(null);
  const [view, setView] = useState<"search" | "list" | "detail" | "cooking">("search");

  // Cooking session state
  const [cookingSession, setCookingSession] = useState<CookingSession | null>(null);
  const [currentStep, setCurrentStep] = useState<CurrentStep | null>(null);
  const [timerActive, setTimerActive] = useState(false);
  const [timerSeconds, setTimerSeconds] = useState(0);

  const { toast } = useToast();

  // Timer effect
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (timerActive && timerSeconds > 0) {
      interval = setInterval(() => {
        setTimerSeconds((sec) => {
          if (sec <= 1) {
            setTimerActive(false);
            toast({
              title: "Timer finished! 🔔",
              description: "Your cooking step is complete.",
            });
            return 0;
          }
          return sec - 1;
        });
      }, 1000);
    } else if (!timerActive && timerSeconds !== 0) {
      clearInterval(interval!);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [timerActive, timerSeconds, toast]);

  // Image upload handler
  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileError("");
    const form = new FormData();
    form.append("file", file);

    try {
      const res = await fetch("http://localhost:8000/agent/detect-ingredients", {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || "Detection failed");
      }
      const { ingredients: detected } = await res.json();
      setIngredients((old) => Array.from(new Set([...old, ...detected])));
      toast({
        title: "Ingredients detected!",
        description: `Found ${detected.length} ingredients in your image.`,
      });
    } catch (err) {
      console.error(err);
      setFileError("Could not detect ingredients from image.");
    }
  };

  // Manual text entry handler
  const handleAddIngredient = () => {
    const val = inputValue.trim();
    if (!val) return;
    
    // Split by commas and add each ingredient
    const newIngredients = val.split(',').map(item => item.trim()).filter(item => item);
    setIngredients((old) => Array.from(new Set([...old, ...newIngredients])));
    setInputValue("");
  };

  // Chip removal handler
  const handleRemoveIngredient = (idx: number) => {
    setIngredients((old) => old.filter((_, i) => i !== idx));
  };

  // Search handler
  const handleSearch = async () => {
    if (ingredients.length === 0) {
      toast({
        title: "No ingredients",
        description: "Please add or detect at least one ingredient.",
        variant: "destructive",
      });
      return;
    }
    setLoading(true);
    setError("");
    setRecipes([]);
    setView("search");

    try {
      const res = await fetch("http://localhost:8000/agent/smart-search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ingredients }),
      });
      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        const recs = typeof data.recipes === "string" ? JSON.parse(data.recipes) : data.recipes;
        setRecipes(recs);
        setView("list");
      }
    } catch (err) {
      setError(`Search failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setLoading(false);
    }
  };

  // Recipe list click handler
  const handleRecipeClick = (recipe: Recipe) => {
    setSelectedRecipe(recipe);
    setView("detail");
  };

  // Start cooking
  const handleStartCooking = async () => {
    if (!selectedRecipe?.sous_chef_format) {
      setError("This recipe doesn't have cooking steps available.");
      return;
    }
    setLoading(true);
    setError("");

    try {
      const res = await fetch("http://localhost:8000/cooking/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sous_chef_format: selectedRecipe.sous_chef_format,
          recipe_summary: selectedRecipe.summary,
        }),
      });
      const data = await res.json();

      if (res.ok && data.session_id) {
        setCookingSession(data);
        setCurrentStep({
          number: data.current_step,
          text: data.step_text,
          hasTimer: data.has_timer,
          total: data.total_steps,
        });
        setView("cooking");
      } else {
        setError(data.detail || "Failed to start cooking session");
      }
    } catch (err) {
      setError(`Failed to start cooking: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setLoading(false);
    }
  };

  // Next cooking step
  const handleNextStep = async () => {
    if (!cookingSession) return;
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/cooking/next", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: cookingSession.session_id,
          command: "next",
        }),
      });
      const data = await res.json();
      if (data.completed) {
        toast({
          title: "Cooking Complete! 🎉",
          description: data.message,
        });
        handleBackToDetail();
      } else {
        setCurrentStep({
          number: data.current_step,
          text: data.step_text,
          hasTimer: data.has_timer,
          total: data.total_steps,
        });
      }
    } catch (err) {
      setError(`Failed to advance step: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setLoading(false);
    }
  };

  // Start timer in cooking view
  const handleStartTimer = () => {
    const text = currentStep?.text.toLowerCase() || "";
    let seconds = 0;
    const minuteMatch = text.match(/(\d+)\s*minute/);
    const secondMatch = text.match(/(\d+)\s*second/);
    if (minuteMatch) seconds += parseInt(minuteMatch[1], 10) * 60;
    if (secondMatch) seconds += parseInt(secondMatch[1], 10);
    if (seconds <= 0) seconds = 30;
    setTimerSeconds(seconds);
    setTimerActive(true);
  };

  // Format timer display
  const formatTime = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  // Navigation handlers
  const handleBackToDetail = () => {
    setCookingSession(null);
    setCurrentStep(null);
    setTimerActive(false);
    setTimerSeconds(0);
    setView("detail");
  };

  const handleBackToList = () => {
    setSelectedRecipe(null);
    setView("list");
  };

  const handleNewSearch = () => {
    setIngredients([]);
    setRecipes([]);
    setSelectedRecipe(null);
    setInputValue("");
    setError("");
    setView("search");
  };

  if (view === "search") {
    return (
      <div className="min-h-screen bg-gradient-subtle">
        {/* Header */}
        <header className="relative z-10 p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <img 
                src="/lovable-uploads/51bd0746-cc07-45bf-844f-aaf5ede5c0b8.png" 
                alt="Sous Chef Logo" 
                className="h-8 w-8 brightness-0 invert"
              />
              <h1 className="font-playfair text-2xl font-bold text-white">
                Super Spoon
              </h1>
            </div>
            <button className="text-white/80 hover:text-white">
              <Menu className="h-6 w-6" />
            </button>
          </div>
        </header>

        {/* Hero Section */}
        <div className="relative overflow-hidden bg-gradient-warm">
          <div className="absolute inset-0 bg-black/20"></div>
          <div className="relative container mx-auto px-4 py-16 text-center">
            <div className="mx-auto max-w-4xl">
              <div className="mb-8 inline-flex h-20 w-20 items-center justify-center rounded-full bg-white/10 backdrop-blur-sm border border-white/20">
                <ChefHat className="h-10 w-10 text-white" />
              </div>
              <h1 className="font-serif text-5xl md:text-6xl font-bold text-white mb-6 tracking-tight">
                AI Recipe Suggestor
              </h1>
              <p className="text-xl text-white/90 mb-12 max-w-2xl mx-auto leading-relaxed font-light">
                Transform your ingredients into culinary masterpieces with AI-powered recipe suggestions
              </p>
            </div>
          </div>
        </div>
        
        {/* Search Section */}
        <div className="relative -mt-12 container mx-auto px-4 pb-20">
          <Card className="mx-auto max-w-3xl shadow-2xl border-0 bg-white/95 backdrop-blur-sm">
            <CardContent className="p-8">
              <div className="space-y-6">
                <div className="text-center">
                  <h2 className="text-2xl font-semibold text-foreground mb-2">What's in your kitchen?</h2>
                  <p className="text-muted-foreground">Upload a photo or enter ingredients manually</p>
                </div>
                
                {/* Image Upload Section */}
                <div className="space-y-4">
                  <div className="text-center">
                    <label className="cursor-pointer inline-flex items-center gap-2 px-6 py-3 bg-gradient-warm text-white rounded-lg hover:opacity-90 transition-opacity">
                      <Upload className="h-5 w-5" />
                      Upload Food Photo
                      <input 
                        type="file" 
                        accept="image/*" 
                        onChange={handleImageUpload}
                        className="hidden"
                      />
                    </label>
                    {fileError && (
                      <p className="text-destructive text-sm mt-2">{fileError}</p>
                    )}
                  </div>
                  
                  <div className="text-center text-muted-foreground">
                    or
                  </div>
                  
                  {/* Manual Entry */}
                  <div className="flex gap-2">
                    <Input
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      placeholder="Type ingredients (use commas to separate multiple items)"
                      className="flex-1"
                      onKeyDown={(e) => e.key === 'Enter' && handleAddIngredient()}
                    />
                    <Button onClick={handleAddIngredient} size="sm">
                      Add
                    </Button>
                  </div>
                  
                  {/* Ingredient Chips */}
                  {ingredients.length > 0 && (
                    <div className="flex flex-wrap gap-2 p-4 bg-muted/30 rounded-lg">
                      {ingredients.map((ing, i) => (
                        <Badge key={i} variant="secondary" className="flex items-center gap-1">
                          {ing}
                          <button 
                            onClick={() => handleRemoveIngredient(i)}
                            className="ml-1 hover:text-destructive"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                  
                  <Button 
                    onClick={handleSearch} 
                    disabled={loading || ingredients.length === 0}
                    className="w-full h-14 text-lg font-semibold bg-gradient-warm hover:opacity-90 transition-all duration-300 shadow-lg hover:shadow-xl disabled:opacity-50"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                        Searching...
                      </>
                    ) : (
                      <>
                        <Search className="mr-2 h-5 w-5" />
                        Find Recipes ({ingredients.length} ingredients)
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {error && (
            <Alert className="mx-auto max-w-3xl mt-6 border-destructive/50 bg-destructive/5">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription className="whitespace-pre-wrap font-medium">
                {error}
              </AlertDescription>
            </Alert>
          )}
        </div>
        
        {/* Features Section */}
        <div className="bg-white py-20">
          <div className="container mx-auto px-4">
            <div className="mx-auto max-w-4xl text-center mb-16">
              <h3 className="font-serif text-3xl font-semibold text-foreground mb-4">Why Choose Our AI Chef?</h3>
              <p className="text-lg text-muted-foreground">Discover the power of intelligent cooking assistance</p>
            </div>
            
            <div className="grid gap-8 md:grid-cols-3">
              <div className="text-center group">
                <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-gradient-warm text-white shadow-lg group-hover:shadow-xl transition-shadow duration-300">
                  <Upload className="h-8 w-8" />
                </div>
                <h4 className="font-semibold text-xl text-foreground mb-3">Photo Recognition</h4>
                <p className="text-muted-foreground leading-relaxed">Upload a photo of your ingredients and let AI identify them automatically</p>
              </div>
              
              <div className="text-center group">
                <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-gradient-warm text-white shadow-lg group-hover:shadow-xl transition-shadow duration-300">
                  <PlayCircle className="h-8 w-8" />
                </div>
                <h4 className="font-semibold text-xl text-foreground mb-3">Interactive Cooking</h4>
                <p className="text-muted-foreground leading-relaxed">Step-by-step cooking guidance with timers and progress tracking</p>
              </div>
              
              <div className="text-center group">
                <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-gradient-warm text-white shadow-lg group-hover:shadow-xl transition-shadow duration-300">
                  <Shield className="h-8 w-8" />
                </div>
                <h4 className="font-semibold text-xl text-foreground mb-3">Food Safety</h4>
                <p className="text-muted-foreground leading-relaxed">Every recipe includes comprehensive food safety guidelines</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (view === "list") {
    return (
      <div className="min-h-screen bg-gradient-subtle">
        {/* Header */}
        <header className="relative z-10 p-6 bg-white/90 backdrop-blur-sm border-b border-border/50">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 cursor-pointer" onClick={handleNewSearch}>
              <img 
                src="/lovable-uploads/51bd0746-cc07-45bf-844f-aaf5ede5c0b8.png" 
                alt="Super Spoon Logo" 
                className="h-8 w-8"
              />
              <h1 className="font-playfair text-2xl font-bold text-foreground">
                Super Spoon
              </h1>
            </div>
            <Button 
              onClick={handleNewSearch}
              variant="outline"
              className="border-primary/20 hover:bg-primary/5"
            >
              <Search className="w-4 h-4 mr-2" />
              New Search
            </Button>
          </div>
        </header>

        <div className="max-w-6xl mx-auto p-6">
          {/* Results Header */}
          <div className="mb-8 animate-fade-in">
            <h2 className="text-3xl font-bold text-foreground mb-2">Recipe Results</h2>
            <p className="text-muted-foreground">Found {recipes.length} delicious recipes for you</p>
          </div>

          {/* Recipe Grid */}
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {recipes.map((recipe, i) => (
              <Card 
                key={i}
                onClick={() => handleRecipeClick(recipe)}
                className="cursor-pointer group hover:shadow-card transition-all duration-300 bg-gradient-card border-0 animate-slide-up hover:scale-[1.02]"
                style={{ animationDelay: `${i * 0.1}s` }}
              >
                <CardHeader className="pb-4">
                  <CardTitle className="text-xl group-hover:text-primary transition-smooth line-clamp-2">
                    {recipe.summary?.title || "Untitled Recipe"}
                  </CardTitle>
                  <CardDescription className="line-clamp-3">
                    {recipe.summary?.description || "No description available"}
                  </CardDescription>
                </CardHeader>
                
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <Users className="w-4 h-4" />
                      <span>Serves {recipe.summary?.serves || "N/A"}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Star className="w-4 h-4" />
                      <span>{recipe.summary?.difficulty || "N/A"}</span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between">
                    <Button
                      variant="ghost"
                      size="sm"
                      asChild
                      onClick={(e) => e.stopPropagation()}
                      className="text-primary hover:text-primary-foreground hover:bg-primary"
                    >
                      <a
                        href={recipe.summary?.link}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-2"
                      >
                        <ExternalLink className="w-4 h-4" />
                        View Recipe
                      </a>
                    </Button>
                    
                    {recipe.sous_chef_format && (
                      <Badge variant="secondary" className="bg-accent/10 text-accent border-accent/20">
                        <PlayCircle className="w-3 h-3 mr-1" />
                        Interactive
                      </Badge>
                    )}
                  </div>

                  {recipe.summary?.food_safety_summary && (
                    <div className="p-3 bg-accent/5 rounded-lg border border-accent/10">
                      <p className="text-sm text-accent flex items-start gap-2">
                        <Shield className="w-4 h-4 mt-0.5 flex-shrink-0" />
                        {recipe.summary.food_safety_summary}
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (view === "detail" && selectedRecipe) {
    const { summary, details, sous_chef_format } = selectedRecipe;
    return (
      <div className="min-h-screen bg-gradient-subtle">
        {/* Header */}
        <header className="relative z-10 p-6 bg-white/90 backdrop-blur-sm border-b border-border/50">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 cursor-pointer" onClick={handleNewSearch}>
              <img 
                src="/lovable-uploads/51bd0746-cc07-45bf-844f-aaf5ede5c0b8.png" 
                alt="Super Spoon Logo" 
                className="h-8 w-8"
              />
              <h1 className="font-playfair text-2xl font-bold text-foreground">
                Super Spoon
              </h1>
            </div>
            <Button 
              onClick={handleBackToList}
              variant="outline"
              className="border-primary/20 hover:bg-primary/5"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Results
            </Button>
          </div>
        </header>

        <div className="max-w-4xl mx-auto p-6">
          {/* Action Buttons */}
          <div className="flex items-center gap-4 mb-8 animate-fade-in">
            
            {sous_chef_format && (
              <Button 
                onClick={handleStartCooking} 
                size="lg"
                className="bg-gradient-warm hover:opacity-90"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Starting...
                  </>
                ) : (
                  <>
                    <PlayCircle className="w-4 h-4 mr-2" />
                    Start Cooking
                  </>
                )}
              </Button>
            )}
          </div>

          {/* Recipe Header */}
          <Card className="mb-8 bg-gradient-card border-0 shadow-card animate-slide-up">
            <CardHeader className="text-center pb-6">
              <CardTitle className="text-4xl font-bold mb-4">
                {summary?.title || "Untitled Recipe"}
              </CardTitle>
              <div className="flex items-center justify-center gap-6 text-muted-foreground mb-4 flex-wrap">
                <div className="flex items-center gap-2">
                  <Clock className="w-5 h-5" />
                  <span>Prep: {details?.prep_time || "N/A"}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Clock className="w-5 h-5" />
                  <span>Cook: {details?.cook_time || "N/A"}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Users className="w-5 h-5" />
                  <span>Serves {summary?.serves || "N/A"}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Star className="w-5 h-5" />
                  <span>{summary?.difficulty || "N/A"}</span>
                </div>
              </div>
              <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-4">
                {summary?.description || "No description available"}
              </p>
              
              {sous_chef_format && (
                <div className="p-4 bg-accent/10 rounded-lg border border-accent/20 mb-4">
                  <p className="text-accent font-medium flex items-center justify-center gap-2">
                    <PlayCircle className="w-5 h-5" />
                    Interactive Cooking Available! {Object.keys(sous_chef_format.steps).length} guided steps
                  </p>
                </div>
              )}
              
              <Button asChild className="bg-gradient-warm hover:shadow-glow transition-all duration-300">
                <a
                  href={summary?.link}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2"
                >
                  <ExternalLink className="w-4 h-4" />
                  View Original Recipe
                </a>
              </Button>
            </CardHeader>
          </Card>

          {error && (
            <Alert className="mb-6 border-destructive/50 bg-destructive/5">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <div className="grid lg:grid-cols-2 gap-8">
            {/* Ingredients */}
            <Card className="bg-gradient-card border-0 shadow-card animate-slide-up" style={{ animationDelay: '0.1s' }}>
              <CardHeader>
                <CardTitle className="text-2xl flex items-center gap-3">
                  <div className="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center">
                    <ChefHat className="w-4 h-4 text-primary" />
                  </div>
                  Ingredients
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3">
                  {(details?.ingredients || []).map((item, idx) => (
                    <li key={idx} className="flex items-start gap-3 p-3 bg-muted/30 rounded-lg">
                      <div className="w-2 h-2 bg-primary rounded-full mt-2.5 flex-shrink-0"></div>
                      <span className="text-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            {/* Method & Techniques */}
            <Card className="bg-gradient-card border-0 shadow-card animate-slide-up" style={{ animationDelay: '0.2s' }}>
              <CardHeader>
                <CardTitle className="text-2xl flex items-center gap-3">
                  <div className="w-8 h-8 bg-accent/10 rounded-full flex items-center justify-center">
                    <Lightbulb className="w-4 h-4 text-accent" />
                  </div>
                  Method & Techniques
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <h4 className="font-semibold mb-3 text-foreground">Cooking Method</h4>
                  <p className="text-muted-foreground leading-relaxed">
                    {details?.method_overview || "No method provided"}
                  </p>
                </div>
                
                {details?.key_techniques && details.key_techniques.length > 0 && (
                  <div>
                    <h4 className="font-semibold mb-3 text-foreground">Key Techniques</h4>
                    <ul className="space-y-2">
                      {details.key_techniques.map((tech, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <div className="w-1.5 h-1.5 bg-accent rounded-full mt-2.5 flex-shrink-0"></div>
                          <span className="text-muted-foreground">{tech}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Food Safety */}
            <Card className="bg-gradient-card border-0 shadow-card animate-slide-up" style={{ animationDelay: '0.3s' }}>
              <CardHeader>
                <CardTitle className="text-2xl flex items-center gap-3">
                  <div className="w-8 h-8 bg-destructive/10 rounded-full flex items-center justify-center">
                    <Shield className="w-4 h-4 text-destructive" />
                  </div>
                  Food Safety
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {details?.food_safety_details?.temperature_guidelines && (
                  <div>
                    <h4 className="font-medium text-foreground mb-2">Temperature</h4>
                    <p className="text-muted-foreground text-sm">{details.food_safety_details.temperature_guidelines}</p>
                  </div>
                )}
                {details?.food_safety_details?.storage_instructions && (
                  <div>
                    <h4 className="font-medium text-foreground mb-2">Storage</h4>
                    <p className="text-muted-foreground text-sm">{details.food_safety_details.storage_instructions}</p>
                  </div>
                )}
                {details?.food_safety_details?.handling_tips && (
                  <div>
                    <h4 className="font-medium text-foreground mb-2">Handling</h4>
                    <p className="text-muted-foreground text-sm">{details.food_safety_details.handling_tips}</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Chef Tips */}
            {details?.chef_tips && details.chef_tips.length > 0 && (
              <Card className="bg-gradient-card border-0 shadow-card animate-slide-up" style={{ animationDelay: '0.4s' }}>
                <CardHeader>
                  <CardTitle className="text-2xl flex items-center gap-3">
                    <div className="w-8 h-8 bg-secondary/10 rounded-full flex items-center justify-center">
                      <Sparkles className="w-4 h-4 text-secondary" />
                    </div>
                    Chef Tips
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-3">
                    {details.chef_tips.map((tip, idx) => (
                      <li key={idx} className="flex items-start gap-3 p-3 bg-secondary/5 rounded-lg">
                        <div className="w-2 h-2 bg-secondary rounded-full mt-2.5 flex-shrink-0"></div>
                        <span className="text-foreground text-sm">{tip}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (view === "cooking" && cookingSession && currentStep) {
    const progress = (currentStep.number / currentStep.total) * 100;
    return (
      <div className="min-h-screen bg-gradient-subtle">
        {/* Header */}
        <header className="relative z-10 p-6 bg-white/90 backdrop-blur-sm border-b border-border/50">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 cursor-pointer" onClick={handleNewSearch}>
              <img 
                src="/lovable-uploads/51bd0746-cc07-45bf-844f-aaf5ede5c0b8.png" 
                alt="Super Spoon Logo" 
                className="h-8 w-8"
              />
              <h1 className="font-playfair text-2xl font-bold text-foreground">
                Super Spoon
              </h1>
            </div>
            <Button 
              onClick={handleBackToDetail}
              variant="outline"
              className="border-primary/20 hover:bg-primary/5"
            >
              Exit Cooking
            </Button>
          </div>
        </header>

        <div className="max-w-4xl mx-auto p-6">
          {/* Cooking Header */}
          <div className="mb-8 animate-fade-in">
            <h2 className="text-3xl font-bold text-foreground mb-2 flex items-center gap-3">
              <PlayCircle className="w-8 h-8 text-primary" />
              {cookingSession.recipe_name}
            </h2>
            <p className="text-muted-foreground">Interactive cooking mode</p>
          </div>

          {/* Progress */}
          <Card className="mb-8 bg-gradient-card border-0 shadow-card animate-slide-up">
            <CardContent className="pt-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-foreground">
                    Step {currentStep.number} of {currentStep.total}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {Math.round(progress)}% complete
                  </span>
                </div>
                <Progress value={progress} className="h-3" />
              </div>
            </CardContent>
          </Card>

          {/* Current Step */}
          <Card className="mb-8 bg-gradient-card border-0 shadow-card animate-slide-up">
            <CardHeader>
              <CardTitle className="text-2xl flex items-center gap-3">
                <div className="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center">
                  <span className="text-primary font-bold">{currentStep.number}</span>
                </div>
                Step {currentStep.number}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-lg leading-relaxed text-foreground mb-6">
                {currentStep.text}
              </p>

              {/* Timer Display */}
              {timerActive && (
                <div className="text-center mb-6">
                  <div className="inline-flex items-center justify-center w-32 h-32 bg-primary/10 rounded-full border-4 border-primary/20">
                    <span className="text-4xl font-bold text-primary">
                      {formatTime(timerSeconds)}
                    </span>
                  </div>
                </div>
              )}

              {error && (
                <Alert className="mb-6 border-destructive/50 bg-destructive/5">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              {/* Action Buttons */}
              <div className="flex gap-4 justify-center">
                {currentStep.hasTimer && !timerActive && (
                  <Button 
                    onClick={handleStartTimer}
                    variant="outline"
                    className="border-accent/20 hover:bg-accent/5"
                  >
                    <Timer className="w-4 h-4 mr-2" />
                    Start Timer
                  </Button>
                )}
                <Button 
                  onClick={handleNextStep} 
                  size="lg"
                  className="bg-gradient-warm hover:opacity-90"
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Loading...
                    </>
                  ) : (
                    <>
                      <SkipForward className="w-4 h-4 mr-2" />
                      Next Step
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return null;
};

export default RecipeSearch;
