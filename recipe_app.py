import pandas as pd
import streamlit as st
import requests
import random
from transformers import pipeline

st.set_page_config(page_title="Weekly Meal Planner", page_icon="🍽", layout="wide")

#API Key for Spoonacular
SPOONACULAR_API_KEY = "a61d3d80b1b24a28a7b32f8e4e70926b"
BASE_URL = "https://api.spoonacular.com/recipes/complexSearch"

#Load Sentiment Analysis Model
@st.cache_resource
def load_sentiment_model():
    """Cache sentiment model to prevent reloading."""
    MODEL_NAME = "distilbert/distilbert-base-uncased-finetuned-sst-2-english"
    return pipeline("sentiment-analysis", model=MODEL_NAME)

sentiment_pipeline = load_sentiment_model()

#Mood-Based Preferred Ingredients
mood_foods = {
    "HAPPY": ["fruit", "salad", "smoothie", "yogurt", "grilled chicken", "berries", "honey", "coconut", "avocado", "oranges"],
    "STRESSED": ["soup", "whole grain", "dark chocolate", "rice", "pasta", "green tea", "bananas", "oats", "pumpkin seeds", "spinach"],
    "TIRED": ["lean protein", "whole grain", "citrus", "nuts", "oatmeal", "coffee", "eggs", "watermelon", "chia seeds", "lentils"],
    "SAD": ["salmon", "nuts", "eggs", "spinach", "avocado", "blueberries", "dark chocolate", "turmeric", "walnuts", "green tea"],
    "ANXIOUS": ["chamomile", "yogurt", "turmeric", "almonds", "tea", "leafy greens", "blueberries", "fermented foods", "oranges", "asparagus"],
    "FOCUSED": ["eggs", "nuts", "dark chocolate", "blueberries", "green tea", "avocado", "beets", "broccoli", "pumpkin seeds", "salmon"],
    "ENERGETIC": ["banana", "oatmeal", "quinoa", "sweet potato", "chicken", "oranges", "watermelon", "chia seeds", "yogurt", "dates"],
    "RELAXED": ["chamomile", "herbal tea", "honey", "oats", "lavender", "almonds", "dark chocolate", "warm milk", "walnuts", "spinach"]
}

params_list = {
    "apiKey": SPOONACULAR_API_KEY,
    "number": 150,
    "addRecipeInformation": True,
    "includeNutrition": True
}

def analyze_mood(mood_text):
    #Use NLP model to analyze user mood
    result = sentiment_pipeline(mood_text)
    return result[0]['label'].upper()

def calculate_calories(age, gender, weight, height, activity_level):
    #Use Mifflin-St Jeor Equation to calculate daily caloric needs
    if gender == "Male":
        bmr = 88.36 + (13.4 * weight) + (4.8 * height) - (5.7 * age)
    else:
        bmr = 447.6 + (9.2 * weight) + (3.1 * height) - (4.3 * age)

    activity_multipliers = {"Sedentary": 1.2, "Light": 1.375, "Moderate": 1.55, "Active": 1.725}
    return round(bmr * activity_multipliers.get(activity_level, 1.2), 2)

def get_recipes(params):
    response = requests.get(BASE_URL, params=params_list)
    data = response.json()

    return data["results"]

def get_weekly_meal_plan(allowed_ingredients, allergens, preferred_cuisine, caloric_needs):
    params = params_list
    recipes = get_recipes(params)
    recipe_count = {} #track recipes to avoid repetition, max 3 times per week

    week_plan = {day: {"Breakfast": None, "Lunch": None, "Snack": None, "Dinner": None} for day in 
                 ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]} 
    
    if allowed_ingredients:
        params["includeIngredients"] = ",".join(allowed_ingredients)
    if allergens:
        params["excludeIngredients"] = ",".join(allergens)
    if preferred_cuisine and "Any" not in preferred_cuisine:
        params["cuisine"] = ",".join(preferred_cuisine)

    if not recipes:        
        params.pop("includeIngredients", None)
        recipes = get_recipes(params)

        if not recipes:
            params.pop("cuisine", None)
            recipes = get_recipes(params)

        if not recipes:
            params.pop("maxCalories", None)
            params.pop("minCalories", None)
            recipes = get_recipes(params)

        if not recipes:
            st.warning("⚠ Still no matches! Using random recipes instead.")
            recipes = get_recipes({"apiKey": SPOONACULAR_API_KEY, "number": 100})

    for day in week_plan:
        used_recipes = set()  #no duplicate meals per day

        for meal_type in ["Breakfast", "Lunch", "Snack", "Dinner"]:
            #filter recipes based on user inputs
            available_recipes = [ 
                r for r in recipes 
                if recipe_count.get(r['id'], 0) < 3  
                and r['id'] not in used_recipes 
                and not any(allergen.lower() in (ing["name"].lower() for ing in r.get("extendedIngredients", [])) for allergen in allergens)  # Allergen-safe
            ]

            #always show a meal per day of the week
            if available_recipes:
                random.shuffle(available_recipes) 
                chosen_recipe = available_recipes[0]
                for recipe in available_recipes:
                    if recipe_count.get(recipe['id'], 0) < 3: 
                        chosen_recipe = recipe
                        break
            else:
                chosen_recipe = random.choice(recipes)  

            if not available_recipes:
                available_recipes = [r for r in recipes if recipe_count.get(r['id'], 0) < 3]

            if not available_recipes:
                available_recipes = recipes  

            if chosen_recipe:
                week_plan[day][meal_type] = chosen_recipe
                recipe_count[chosen_recipe['id']] = recipe_count.get(chosen_recipe['id'], 0) + 1
                used_recipes.add(chosen_recipe['id'])
            else:
                st.warning(f"⚠️ No recipes found for {meal_type} on {day}.")

    return week_plan

def convert_meal_plan_to_csv(week_plan): #to download meal plan
    rows = []

    for day, meals in week_plan.items():
        for meal_type, meal in meals.items():
            if meal:
                rows.append([day, meal_type, meal["title"], meal.get("sourceUrl", "N/A")])

    df = pd.DataFrame(rows, columns=["Day", "Meal Type", "Recipe", "URL"])
    return df.to_csv(index=False).encode("utf-8")

def fetch_recipe_info(recipe_id):
    url = f"https://api.spoonacular.com/recipes/{recipe_id}/information"
    response = requests.get(url, params=params_list) 

    if response.status_code == 200:
        return response.json()
    return {}  

def fetch_ingredients(recipe_id):
    url = f"https://api.spoonacular.com/recipes/{recipe_id}/ingredientWidget.json"
    response = requests.get(url, params=params_list) 

    if response.status_code == 200:
        return response.json().get("ingredients", [])
    return []  

def compute_total_shopping_cost(shopping_list):
    url = "https://api.spoonacular.com/mealplanner/shopping-list/compute"
    headers = {"Content-Type": "application/json"}
    params = params_list

    shopping_items = [f"{v['amount']} {v['unit']} {k}" for k, v in shopping_list.items()]
    payload = {"items": shopping_items}
    response = requests.post(url, headers=headers, params=params, json=payload)

    if response.status_code == 200:
        shopping_data = response.json()
        total_cost = sum(item.get("measures", {}).get("metric", {}).get("amount", 0) for aisle in shopping_data["aisles"] for item in aisle["items"])
        return total_cost, shopping_data["aisles"]
    else:
        st.error(f"❌ Failed to compute shopping list cost: {response.json()}")
        return 0.0, []

def generate_shopping_list(week_plan):
    shopping_list = {}

    for day, meals in week_plan.items():
        for meal_type, meal in meals.items():
            if not meal or "id" not in meal:
                continue 

            recipe_id = meal["id"]
            recipe_info = fetch_recipe_info(recipe_id)

            servings = recipe_info.get("servings")
            if not servings:
                continue  

            ingredients = fetch_ingredients(recipe_id)
            if not ingredients:
                continue  

            for ingredient in ingredients:
                name = ingredient["name"].lower()
                total_amount = ingredient["amount"]["metric"]["value"]
                unit = ingredient["amount"]["metric"]["unit"]
                amount_per_serving = total_amount / servings  

                if name in shopping_list:
                    shopping_list[name]["amount"] += amount_per_serving
                else:
                    shopping_list[name] = {"amount": amount_per_serving, "unit": unit}

    total_cost, aisles = compute_total_shopping_cost(shopping_list)
    return shopping_list, total_cost, aisles

def main():
    st.title("🍽 Weekly Meal Planner")
    st.write(
        """
        Hi, welcome to **RecipeGPT**, your personalized weekly meal planner! 
        We recommend recipes based on your **caloric needs, cuisine preferences, favorite ingredients, and mood**.

        🔍 **How Mood Affects Recommendations:**  
        - **Happy?** 😊 Get light, fresh meals like fruit, salads, and smoothies.  
        - **Stressed?** 😟 Try comfort foods like soup, whole grains, and dark chocolate.  
        - **Tired?** 😴 Get energy from lean proteins, whole grains, and citrus fruits.  
        - **Sad?** 😢 Eat foods rich in Omega-3 (salmon, nuts, eggs) for a mood boost.  
        - **Anxious?** 😨 Calming foods like chamomile tea, yogurt, and turmeric can help.  
        """
    )

    #User inputs
    st.sidebar.header("👤 User Profile")
    age = st.sidebar.slider("Age", 18, 80, 25)
    gender = st.sidebar.selectbox("Gender", ["Male", "Female"])
    weight = st.sidebar.number_input("Weight (kg)", min_value=40, max_value=150, value=70)
    height = st.sidebar.number_input("Height (cm)", min_value=140, max_value=210, value=175)
    activity_level = st.sidebar.selectbox("Activity Level", ["Sedentary", "Light", "Moderate", "Active"])
    preferred_cuisine = st.sidebar.multiselect("Preferred Cuisines", ["Any", "Italian", "Mexican", "Japanese", "Chinese", "French"])
    mood_text = st.sidebar.text_area("How are you feeling today?", "I am feeling happy and energetic.")
    all_ingredients = ["Chicken", "Beef", "Rice", "Pasta", "Tomatoes", "Garlic", "Onions", "Eggs", "Milk", "Spinach"]
    allowed_ingredients = st.sidebar.multiselect("✅ Select Ingredients", all_ingredients)
    allergens = st.sidebar.multiselect("🚫 Allergens / Dietary Restrictions", ["Dairy", "Gluten", "Nuts", "Shellfish", "Soy", "Eggs"])

    if st.sidebar.button("✨ Generate Weekly Plan"):
        caloric_needs = calculate_calories(age, gender, weight, height, activity_level)
        week_plan = get_weekly_meal_plan(
            allowed_ingredients, allergens, preferred_cuisine, caloric_needs
        )

        tab_names = ["📅 Weekly Overview", "🛒 Shopping List", "🍽 Monday", "🍽 Tuesday", "🍽 Wednesday", "🍽 Thursday", "🍽 Friday", "🍽 Saturday", "🍽 Sunday"]
        tabs = st.tabs(tab_names)

        #Main tab - summary
        with tabs[0]:  
            st.markdown("### 📅 Weekly Meal Plan Summary")
            st.info("ℹ️ **Note:** Recipes may be repeated at most three times throughout the week to ensure variety.")

            for day, meals in week_plan.items():
                st.markdown(f"#### 🍽 {day}")
                for meal_type, meal in meals.items():
                    if meal:
                        st.markdown(f"  - **{meal_type}**: [{meal['title']}](https://spoonacular.com/recipes/{meal['title'].replace(' ', '-')}-{meal['id']})")

            meal_plan_csv = convert_meal_plan_to_csv(week_plan)
            st.download_button("📥 Download Meal Plan", meal_plan_csv, "meal_plan.csv", "text/csv")

        #Shopping list tab
        with tabs[1]:
            st.markdown("### 🛒 Shopping List (Per Serving)")

            shopping_list, total_cost, aisles = generate_shopping_list(week_plan)

            if shopping_list:
                shopping_list_df = pd.DataFrame([
                    {"Ingredient": k.capitalize(), "Amount": f"{v['amount']} {v['unit']}"}
                    for k, v in shopping_list.items()
                ])
                st.write(f"💰 **Total Estimated Cost (Per Serving):** ${total_cost:.2f}")
                st.table(shopping_list_df)

                st.markdown("### 🏪 Aisle Breakdown")
                for aisle in aisles:
                    st.subheader(aisle["aisle"])
                    for item in aisle["items"]:
                        st.write(f"- {item['name']}: {item['measures']['metric']['amount']} {item['measures']['metric']['unit']}")

                shopping_list_text = "\n".join([
                    f"{k.capitalize()}: {v['amount']} {v['unit']}" for k, v in shopping_list.items()
                ])
                st.download_button("📥 Download Shopping List", shopping_list_text, "shopping_list.txt", "text/plain")
            else:
                st.warning("⚠️ No ingredients found in the meal plan.")

        #Daily tabs - detailed recipes
        for i, (day, meals) in enumerate(week_plan.items(), start=2):
            with tabs[i]:
                st.subheader(f"🍽 {day}'s Meals")

                for meal_type, meal in meals.items():
                    if meal:
                        with st.expander(f"🍴 {meal_type}: {meal.get('title', 'Unknown Recipe')}"):
                            if "image" in meal:
                                st.image(meal["image"], use_container_width=True)
                            else:
                                st.warning("⚠️ No image available for this recipe.")

                            st.write(f"🕒 **Prep Time**: {meal.get('readyInMinutes', 'N/A')} min")

                            # Handle missing nutrition data
                            calories = "N/A"
                            if meal.get("nutrition") and "nutrients" in meal["nutrition"]:
                                for nutrient in meal["nutrition"]["nutrients"]:
                                    if nutrient["name"] == "Calories":
                                        calories = f"{nutrient['amount']} kcal"
                                        break

                            st.write(f"🔥 **Calories**: {calories}")

                            price_per_serving = meal.get("pricePerServing")
                            if price_per_serving is not None:
                                st.write(f"💰 **Cost per Serving**: ${price_per_serving / 100:.2f}")
                            else:
                                st.write(f"💰 **Cost per Serving**: N/A")

                            if "id" in meal and "title" in meal:
                                recipe_url = f"https://spoonacular.com/recipes/{meal['title'].replace(' ', '-')}-{meal['id']}"
                                st.markdown(f"📖 **Full Recipe**: [{meal['title']}]({recipe_url})")
                            else:
                                st.warning("⚠️ Recipe link unavailable.")


if __name__ == "__main__":
    main()