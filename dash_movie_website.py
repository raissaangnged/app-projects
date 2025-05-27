import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State, ALL
import json
import requests
import cohere
import random
import base64
import logging

# Configure logging to suppress SageMaker messages
logging.getLogger('sagemaker').setLevel(logging.ERROR)
logging.getLogger('sagemaker.config').setLevel(logging.ERROR)
logging.getLogger('sagemaker.runtime').setLevel(logging.ERROR)
logging.getLogger('sagemaker.serve').setLevel(logging.ERROR)

website_theme = {
    'background-color': '#f8e8e8',
        'color': '#2C2C2C',
        'font-family': 'Bebas Neue, Poppins, Netflix Sans, Helvetica Neue, Segoe UI, Roboto, Ubuntu, sans-serif',
    'background-image': 'linear-gradient(to right, #FFB6C1, #FFC0CB, #FFE4E1)', 
    'accent-color': '#B0C4DE',  
    'button-color': '#2C2C2C', 
    'button-text-color': 'white',  
    'hover-color': '#90EE90',  
    'active-tab-color': '#FFC0CB'  
}

TMDB_API_KEY = "4afe57e82f20d0e42282fd7af90ebd54"
SPOONACULAR_API_KEY = "4cae760fd04e4227b7f69566e0e20ce0"
COHERE_API_KEY = "NikYbnEnCLeS6DnkQaOf2b5JMXiIJne4LBYInWPg"  

class APIHelpers:
    def __init__(self, tmdb_key, spoonacular_key, cohere_key):
        self.TMDB_API_KEY = tmdb_key
        self.SPOONACULAR_API_KEY = spoonacular_key
        self.COHERE_API_KEY = cohere_key
        self.cohere_client = cohere.Client(self.COHERE_API_KEY)

    def get_comprehensive_media_info(self, media_id, media_type):
        """Fetch detailed media information from TMDB"""
        details_url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={self.TMDB_API_KEY}&append_to_response=credits,reviews,external_ids"
        response = requests.get(details_url).json()
        
        # Extract comprehensive details
        poster_path = response.get('poster_path')
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        
        # Extract cast information
        cast = response.get('credits', {}).get('cast', [])
        top_cast = [f"{actor['name']} as {actor['character']}" for actor in cast[:5]]
        
        # Extract crew information
        crew = response.get('credits', {}).get('crew', [])
        directors = [person['name'] for person in crew if person['job'] == 'Director']
        
        # Extract reviews
        reviews = response.get('reviews', {}).get('results', [])
        sample_reviews = [review['content'][:200] + '...' for review in reviews[:3]]
        
        # Set title 
        title = 'Unknown'
        if 'title' in response:
            title = response['title']
        elif 'name' in response:
            title = response['name']
        
        # Handle runtime safely
        runtime = 'N/A'
        if 'runtime' in response and response['runtime']:
            runtime = response['runtime']
        elif 'episode_run_time' in response and response['episode_run_time'] and len(response['episode_run_time']) > 0:
            runtime = response['episode_run_time'][0]
        
        return {
            'id': response.get('id', media_id), 
            'media_type': media_type, 
            'title': title,
            'overview': response.get('overview', 'No overview available'),
            'poster': poster_url,
            'genres': [genre['name'] for genre in response.get('genres', [])],
            'release_date': response.get('release_date', response.get('first_air_date', 'Unknown')),
            'runtime': runtime,  
            'rating': response.get('vote_average', 'N/A'),
            'directors': directors or ['Not available'],
            'top_cast': top_cast or ['Cast information not available'],
            'reviews': sample_reviews,
            'imdb_id': response.get('external_ids', {}).get('imdb_id')
        }
        
    def search_movies(self, search_value):
        """Search movies and TV shows from TMDB"""
        url = f"https://api.themoviedb.org/3/search/multi?api_key={self.TMDB_API_KEY}&query={search_value}"
        response = requests.get(url).json()
        
        options = []
        for item in response.get('results', []):
            if item['media_type'] in ['movie', 'tv']:
                title = item.get('title', item.get('name', 'Unknown'))
                release_date = item.get('release_date', item.get('first_air_date', ''))
                year = release_date[:4] if release_date else ''
                
                label = f"{title} ({year})" if year else title
                
                options.append({
                    'label': label, 
                    'value': json.dumps({
                        'id': item['id'], 
                        'media_type': item['media_type']
                    })
                })
        
        return options

    def get_recipe_options(self, food_type, media_details):
        """Get recipe options more specifically tied to the media's genre, type, and cultural context using LLM"""
        # Extract media details
        genre = media_details.get('genres', ['Comedy'])[0]
        title = media_details.get('title', '')
        overview = media_details.get('overview', '')
        
        # Use LLM to generate a better, more personalized search query
        try:
            prompt = f"""Generate a specific food search query for Spoonacular API based on this movie info:
            Title: {title}
            Genre: {genre}
            Overview: {overview}
            Food type needed: {food_type}

            Consider the movie's theme, setting, era, cultural background, and emotional tone.
            For example, for an Italian movie and main course, suggest "authentic Italian pasta";
            for a horror movie and dessert, suggest "blood-red velvet cake".
            Return ONLY the search query phrase (3-5 words), no explanations.
            """

            response = self.cohere_client.generate(
                model='command',
                prompt=prompt,
                max_tokens=20,  
                temperature=0.7
            )
            
            llm_search_query = response.generations[0].text.strip()
            
            # Fallback options in case the LLM response isn't usable
            fallback_queries = {
                'Comedy': f'fun party {food_type}',
                'Drama': f'elegant sophisticated {food_type}',
                'Action': f'hearty protein-packed {food_type}',
                'Sci-Fi': f'futuristic molecular gastronomy {food_type}',
                'Horror': f'halloween themed {food_type}',
                'Romance': f'romantic date night {food_type}',
                'Adventure': f'exotic international {food_type}',
                'Animation': f'colorful fun {food_type}',
                'Family': f'crowd-pleasing {food_type}'
            }
            
            # Use LLM result if it looks reasonable, otherwise use fallback
            search_query = llm_search_query if len(llm_search_query.split()) >= 2 else fallback_queries.get(genre, f'{genre} {food_type}')
            
            print(f"Using LLM-generated search query: '{search_query}' for {title} ({food_type})")
            
        except Exception as e:
            print(f"LLM error: {e}, using fallback query")
            # Country/cultural mapping as fallback
            country_food_map = {
                'korean': f'korean {food_type}',
                'japanese': f'japanese {food_type}',
                'italian': f'italian {food_type}',
                'french': f'french {food_type}',
                'mexican': f'mexican {food_type}',
                'indian': f'indian {food_type}',
                'chinese': f'chinese {food_type}'
            }
            
            # Genre-based fallback
            genre_food_map = {
                'Comedy': f'fun party {food_type}',
                'Drama': f'elegant sophisticated {food_type}',
                'Action': f'hearty protein-packed {food_type}',
                'Sci-Fi': f'futuristic molecular gastronomy {food_type}',
                'Horror': f'halloween themed {food_type}',
                'Romance': f'romantic date night {food_type}',
                'Adventure': f'exotic international {food_type}'
            }
            
            # Check for cultural references in title
            for key, value in country_food_map.items():
                if key.lower() in title.lower():
                    search_query = value
                    break
            else:
                # Fallback to genre-based search
                search_query = genre_food_map.get(genre, f'{genre} {food_type}')
        
        # Get recipes from Spoonacular
        url = f"https://api.spoonacular.com/recipes/complexSearch?query={search_query}&number=4&apiKey={self.SPOONACULAR_API_KEY}"
        response = requests.get(url).json()
        
        recipe_options = []
        for recipe in response.get("results", []):
            recipe_options.append({
                'id': recipe['id'],
                'title': recipe['title'],
                'image': recipe['image']
            })
        
        # If no recipes found, use a generic search
        if not recipe_options:
            generic_search = f"{food_type} recipe"
            url = f"https://api.spoonacular.com/recipes/complexSearch?query={generic_search}&number=4&apiKey={self.SPOONACULAR_API_KEY}"
            response = requests.get(url).json()
            
            for recipe in response.get("results", []):
                recipe_options.append({
                    'id': recipe['id'],
                    'title': recipe['title'],
                    'image': recipe['image']
                })
        
        return recipe_options

    def get_detailed_recipe(self, recipe_id):
        """Get detailed recipe information"""
        details_url = f"https://api.spoonacular.com/recipes/{recipe_id}/information?includeNutrition=false&apiKey={self.SPOONACULAR_API_KEY}"
        details_response = requests.get(details_url).json()
        
        return {
            'title': details_response['title'],
            'image': details_response['image'],
            'ingredients': [ing['original'] for ing in details_response.get('extendedIngredients', [])],
            'instructions': details_response.get('instructions', 'No instructions available'),
            'readyInMinutes': details_response.get('readyInMinutes', 'Unknown'),
            'servings': details_response.get('servings', 'Unknown')
        }

    def get_recommended_content(self, media_id, media_type):
        """Get recommended movies/shows"""
        url = f"https://api.themoviedb.org/3/{media_type}/{media_id}/recommendations?api_key={self.TMDB_API_KEY}"
        response = requests.get(url).json()
        
        recommendations = []
        for item in response.get('results', [])[:6]:  # Get top 6 recommendations
            recommendations.append({
                'id': item['id'],
                'title': item.get('title', item.get('name', 'Unknown')),
                'poster': f"https://image.tmdb.org/t/p/w500{item['poster_path']}" if item.get('poster_path') else None,
                'media_type': item['media_type']
            })
        
        return recommendations

class TriviaGame:
    def __init__(self, media_details, cohere_client):
        self.media_details = media_details
        self.cohere_client = cohere_client
        self.questions = self.generate_trivia_questions()
        self.current_question_index = 0 
        self.score = 0  
        self.mistakes = 0  
        self.current_movie = media_details
        self.is_game_over = False
        self.round_number = 1  
        self.total_rounds = 10 

    def restart(self, media_details):
        """Reset the game state with new media details"""
        self.media_details = media_details
        self.current_movie = media_details
        self.questions = self.generate_trivia_questions()
        self.current_question_index = 0 
        self.score = 0 
        self.mistakes = 0 
        self.is_game_over = False
        self.round_number = 1  
        self.total_rounds = 10  

    def generate_trivia_questions(self):
        """Generate trivia questions using Cohere"""
        title = self.media_details['title']
        prompt = f"""Generate 10 multiple-choice trivia questions about the movie or TV show "{title}". 
        Include details about plot, characters, actors, directors, and production.
        
        Format EXACTLY as follows (including the precise prefixes):
        Q: [Question text]
        A: [Option A - correct answer]
        B: [Option B - wrong answer]
        C: [Option C - wrong answer]
        D: [Option D - wrong answer]
        Correct: A
        
        Make sure each question has exactly 4 options (A, B, C, D), and mark the correct answer clearly with "Correct: [letter]".
        Ensure the correct answer is randomly distributed (don't always make A correct).
        
        Examples:
        Q: Who directed the movie "Inception"?
        A: Christopher Nolan
        B: Steven Spielberg
        C: James Cameron
        D: Quentin Tarantino
        Correct: A
        
        Q: Which actor played the character Rose in "Titanic"?
        A: Jennifer Lawrence
        B: Kate Winslet
        C: Emma Watson
        D: Meryl Streep
        Correct: B"""
        
        try:
            response = self.cohere_client.generate(
                model='command',
                prompt=prompt,
                max_tokens=800, 
                temperature=0.7
            )
            trivia_text = response.generations[0].text
            print(f"Generated trivia for {title}:\n{trivia_text[:100]}...")
            
            trivia_questions = []
            current_question = {}
            for line in trivia_text.split('\n'):
                line = line.strip()
                if not line:  
                    continue
                    
                if line.startswith('Q:'):
                    if current_question and 'question' in current_question and 'options' in current_question and len(current_question['options']) >= 4 and 'correct' in current_question:
                        trivia_questions.append(current_question)
                    current_question = {'question': line[2:].strip(), 'options': {}}
                elif line.startswith('A:') and current_question:
                    current_question['options']['A'] = line[2:].strip()
                elif line.startswith('B:') and current_question:
                    current_question['options']['B'] = line[2:].strip()
                elif line.startswith('C:') and current_question:
                    current_question['options']['C'] = line[2:].strip()
                elif line.startswith('D:') and current_question:
                    current_question['options']['D'] = line[2:].strip()
                elif line.startswith('Correct:') and current_question:
                    current_question['correct'] = line[8:].strip()
            
            # Add the last question if it's complete
            if current_question and 'question' in current_question and 'options' in current_question and len(current_question['options']) >= 4 and 'correct' in current_question:
                trivia_questions.append(current_question)
            
            print(f"Successfully parsed {len(trivia_questions)} trivia questions")
            
            # Create default questions if none were generated
            if not trivia_questions:
                print("Creating default questions as fallback")
                trivia_questions = self.create_default_questions(title)
                
            return trivia_questions
        except Exception as e:
            print(f"Trivia generation error: {e}")
            return self.create_default_questions(title)
    
    def create_default_questions(self, title):
        """Create generic questions as fallback"""
        return [
            {
                'question': f"What year was {title} released?",
                'options': {
                    'A': '2018',
                    'B': '2019',
                    'C': '2020', 
                    'D': '2021'
                },
                'correct': 'C'
            },
            {
                'question': f"Which genre best describes {title}?",
                'options': {
                    'A': 'Action',
                    'B': 'Comedy',
                    'C': 'Drama',
                    'D': 'Sci-Fi'
                },
                'correct': 'A'
            },
            {
                'question': f"Who directed {title}?",
                'options': {
                    'A': 'Steven Spielberg',
                    'B': 'Christopher Nolan',
                    'C': 'James Cameron',
                    'D': 'Quentin Tarantino'
                },
                'correct': 'B'
            }
        ]

    def get_current_question(self):
        """Get the current trivia question"""
        if not self.questions or self.current_question_index >= len(self.questions) or self.current_question_index >= 10:
            self.is_game_over = True
            return None
            
        if self.mistakes >= 3:
            self.is_game_over = True
            return None
        
        current_q = self.questions[self.current_question_index]
        
        self.round_number = self.current_question_index + 1
        
        if not current_q.get('options') or not current_q.get('correct'):
            self.current_question_index += 1
            return self.get_current_question()
            
        return current_q

    def check_answer(self, selected_index):
        """Check if the selected answer is correct"""
        print(f"check_answer called - Current state: index={self.current_question_index}, round={self.round_number}, score={self.score}, mistakes={self.mistakes}")
        
        if self.is_game_over:
            return {'correct': False, 'game_over': True}
        
        current_q = self.get_current_question()
        if not current_q:
            self.is_game_over = True
            return {'correct': False, 'game_over': True}
        
        # Convert index to letter (0=A, 1=B, etc.)
        option_letter = chr(65 + selected_index)  # A, B, C, D
        
        is_correct = (option_letter == current_q['correct'])
        
        if is_correct:
            self.score += 1
        else:
            self.mistakes += 1
        
        # Move to next question
        self.current_question_index += 1
        self.round_number = self.current_question_index + 1  # Update round number

        # Check if game should end
        if self.mistakes >= 3 or self.current_question_index >= min(10, len(self.questions)):
            self.is_game_over = True
        
        return {
            'correct': is_correct,
            'score': self.score, 
            'mistakes': self.mistakes,
            'game_over': self.is_game_over
        }

# Initialize API Helpers
api_helpers = APIHelpers(
    tmdb_key=TMDB_API_KEY,
    spoonacular_key=SPOONACULAR_API_KEY,
    cohere_key=COHERE_API_KEY 
)

# Initialize Dash App
app = dash.Dash(__name__, 
                external_stylesheets=[dbc.themes.DARKLY],
                suppress_callback_exceptions=True)  

# Global variables to store state
CURRENT_MEDIA = None
CURRENT_TRIVIA_GAME = None

# App Layout
app.layout = dbc.Container([
    html.Div([
        html.H1("🎬 Movie Night Guide 🍽️", 
                className="text-center my-4",
                style={'color': website_theme['color']})
    ], style={'background-color': website_theme['background-color'], 'padding': '20px 0'}),
    
    # Movie Search Section with More Explicit Instructions
    dbc.Row([
        dbc.Col([
            html.P("🔍 Search for a movie or TV show (type at least 3 characters)", 
                   className="fw-bold", style={'color': 'black'}),
            dcc.Input(
                id="movie_search_input", 
                type="text", 
                placeholder="Type movie/show name...", 
                className="form-control mb-2",
                debounce=True
            ),
            dbc.Button(
                "Search Movies", 
                id="search_movies_btn", 
                color="primary", 
                className="mb-2",
                style={
                    "backgroundColor": website_theme["button-color"],
                    "color": website_theme["button-text-color"],
                    "borderColor": website_theme["button-color"]
                }
            ),
            html.P("👇 Select from the dropdown below", 
                   style={'color': 'black'}),
            dcc.Dropdown(
                id='movie_selection_dropdown',
                placeholder="Select a specific movie/show"
            )
        ], width=12)
    ], className="mb-3"),

    dbc.Tabs([
        dbc.Tab(label="Overview", tab_id="overview_tab", label_style={"color": "black"}, 
                active_label_style={"backgroundColor": website_theme['active-tab-color'], "color": "black"}),
        dbc.Tab(label="Meal Pairing", tab_id="meal_tab", label_style={"color": "black"},
                active_label_style={"backgroundColor": website_theme['active-tab-color'], "color": "black"}),
        dbc.Tab(label="Trivia", tab_id="trivia_tab", label_style={"color": "black"},
                active_label_style={"backgroundColor": website_theme['active-tab-color'], "color": "black"}),
        dbc.Tab(label="Recommended", tab_id="recommended_tab", label_style={"color": "black"},
                active_label_style={"backgroundColor": website_theme['active-tab-color'], "color": "black"})
    ], id="main_tabs", active_tab="overview_tab"),
    
    # Content Display Area
    html.Div(id="tab_content", className="mt-3"),
], fluid=True, style={
    'background-color': website_theme['background-color'],
    'color': website_theme['color'],
    'font-family': website_theme['font-family'],
    'min-height': '100vh'  
})

# Movie Search Callback
@app.callback(
    Output('movie_selection_dropdown', 'options'),
    [Input('search_movies_btn', 'n_clicks')],
    [State('movie_search_input', 'value')]
)
def update_movie_dropdown(n_clicks, search_value):
    if not n_clicks or not search_value or len(search_value) < 3:
        return []
    return api_helpers.search_movies(search_value)

# Tab Content Callback
@app.callback(
    Output('tab_content', 'children'),
    [Input('main_tabs', 'active_tab'),
     Input('movie_selection_dropdown', 'value')]
)
def update_tab_content(active_tab, selected_movie):
    global CURRENT_TRIVIA_GAME
    
    if not selected_movie:
        return html.Div([
            html.H4("Please select a movie or TV show to get started.", 
                    style={'color': 'black', 'textAlign': 'center', 'marginTop': '20px'})
        ])
    
    try:
        movie_info = json.loads(selected_movie)
        
        # For safety, get comprehensive details if needed
        if 'title' not in movie_info:
            try:
                media_id = movie_info['id']
                media_type = movie_info['media_type']
                movie_info = api_helpers.get_comprehensive_media_info(media_id, media_type)
            except Exception as e:
                print(f"Error fetching comprehensive details: {e}")
                return html.Div([
                    html.H4(f"Error loading media details: {str(e)}", 
                           style={'color': 'red', 'textAlign': 'center', 'marginTop': '20px'})
                ])
        
        # Handle tab switching
        if active_tab == 'overview_tab':
            try:
                return create_overview_tab(movie_info)
            except KeyError as e:
                print(f"KeyError in create_overview_tab: {e}")
                return html.Div([
                    html.H4(f"Error displaying overview: Missing '{str(e)}' information", 
                           style={'color': 'red', 'textAlign': 'center', 'marginTop': '20px'})
                ])
        elif active_tab == 'meal_tab':
            try:
                return create_meal_pairing_tab(movie_info)
            except KeyError as e:
                print(f"KeyError in create_meal_pairing_tab: {e}")
                return html.Div([
                    html.H4(f"Error displaying meal pairings: Missing '{str(e)}' information", 
                           style={'color': 'red', 'textAlign': 'center', 'marginTop': '20px'})
                ])
        elif active_tab == 'trivia_tab':
            try:
                print("Creating new trivia game")
                CURRENT_TRIVIA_GAME = None  # Force recreation
                CURRENT_TRIVIA_GAME = TriviaGame(movie_info, api_helpers.cohere_client)
                CURRENT_TRIVIA_GAME.current_question_index = 0
                CURRENT_TRIVIA_GAME.score = 0
                CURRENT_TRIVIA_GAME.mistakes = 0
                CURRENT_TRIVIA_GAME.round_number = 1
                CURRENT_TRIVIA_GAME.is_game_over = False
                print(f"Initial trivia game state: index={CURRENT_TRIVIA_GAME.current_question_index}, round={CURRENT_TRIVIA_GAME.round_number}")
            except KeyError as e:
                print(f"KeyError creating trivia game: {e}")
                return html.Div([
                    html.H4(f"Error creating trivia game: Missing '{str(e)}' information", 
                           style={'color': 'red', 'textAlign': 'center', 'marginTop': '20px'})
                ])
            return create_trivia_tab(CURRENT_TRIVIA_GAME)
        elif active_tab == 'recommended_tab':
            try:
                return create_recommended_tab(movie_info['id'], movie_info['media_type'])
            except KeyError as e:
                print(f"KeyError in create_recommended_tab: {e}")
                return html.Div([
                    html.H4(f"Error displaying recommendations: Missing '{str(e)}' information", 
                           style={'color': 'red', 'textAlign': 'center', 'marginTop': '20px'})
                ])
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        print(f"Error in update_tab_content: {e}")
        return html.Div([
            html.H4(f"An error occurred: {str(e)}", 
                   style={'color': 'red', 'textAlign': 'center', 'marginTop': '20px'})
        ])

def create_overview_tab(media_details):
    return dbc.Card([
        dbc.CardHeader(media_details['title']),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Img(
                        src=media_details['poster'], 
                        style={'max-width': '300px', 'height': 'auto'}
                    )
                ], width=4),
                dbc.Col([
                    html.H4("Overview"),
                    html.P(media_details['overview']),
                    
                    html.H5("Details"),
                    html.P(f"Genres: {', '.join(media_details['genres'])}"),
                    html.P(f"Release Date: {media_details['release_date']}"),
                    html.P(f"Runtime: {media_details['runtime']} minutes"),
                    html.P(f"Rating: {media_details['rating']}/10"),
                    
                    html.H5("Directors"),
                    html.P(", ".join(media_details['directors'])),
                    
                    html.H5("Top Cast"),
                    html.Ul([html.Li(cast) for cast in media_details['top_cast']]),
                ], width=8)
            ]),
            
            # Movie Assistant Chat Section
            html.Div([
                dbc.Card([
                    dbc.CardHeader("Movie Assistant", className="bg-primary text-white"),
                    dbc.CardBody([
                        html.Div(id='movie_chat_messages', className="chat-messages mb-3", style={
                            'height': '300px',
                            'overflow-y': 'auto',
                            'padding': '10px',
                            'border': '1px solid #ddd',
                            'border-radius': '5px',
                            'background-color': '#f8f9fa'
                        }),
                        dbc.InputGroup([
                            dcc.Input(
                                id='movie_chat_input', 
                                type='text', 
                                placeholder='Ask me anything about the movie...',
                                className='form-control'
                            ),
                            dbc.Button(
                                "Send",
                                id='movie_chat_send',
                                color="primary",
                                className="ms-2",
                                style={
                                    "backgroundColor": website_theme["button-color"],
                                    "color": website_theme["button-text-color"],
                                    "borderColor": website_theme["button-color"]
                                }
                            )
                        ])
                    ])
                ])
            ], className="mt-4")
        ])
    ])

def create_meal_pairing_tab(media_details):
    food_types = ['snacks', 'main course', 'dessert']
    recipe_options = {}
    
    for food_type in food_types:
        recipe_options[food_type] = api_helpers.get_recipe_options(food_type, media_details)
    
    recipe_dropdowns = []
    for food_type, options in recipe_options.items():
        dropdown_id = f'{food_type.replace(" ", "_")}_recipe_dropdown'
        
        dropdown = dbc.Row([
            dbc.Col(html.H4(f"{food_type.capitalize()} Options", style={"color": "white"}), width=12),
            dbc.Col([
                dcc.Dropdown(
                    id=dropdown_id,
                    options=[
                        {'label': 'None', 'value': 'none'},
                        *[{'label': recipe['title'], 'value': json.dumps({'id': recipe['id'], 'title': recipe['title']})} 
                          for recipe in options]
                    ],
                    placeholder=f"Select a {food_type}",
                    style={"color": "black"}
                )
            ], width=12)
        ])
        recipe_dropdowns.append(dropdown)
    
    # Add dish recommendations section
    dish_recommendations = get_dish_recommendations(media_details)
    
    return dbc.Card([
        dbc.CardHeader("🍽️ Movie-Inspired Meal Pairing"),
        dbc.CardBody([
            html.H4("Recommended Dishes", className="mb-3", style={"color": "white"}),
            html.P(dish_recommendations, className="mb-4", style={"color": "white"}),
            *recipe_dropdowns,
            html.Div(id='selected_recipes_container'),
            html.Div(id='recipe_details_container'),
            html.Div(id='grocery_list_container')
        ])
    ])

def create_trivia_tab(trivia_game):
    if not trivia_game:
        return dbc.Card([
            dbc.CardHeader(html.H4("Trivia Game", className="card-title")),
            dbc.CardBody([
                html.H4("Welcome to the Trivia Game!", style={"color": "black", "textAlign": "center"}),
                html.P("Select a movie to begin playing the trivia game", style={"color": "black", "textAlign": "center"}),
                html.P("You'll get 10 questions about the movie. Try to answer correctly!", style={"color": "black", "textAlign": "center"}),
                html.P("The game ends when you make 3 mistakes or complete all questions", style={"color": "black", "textAlign": "center"})
            ])
        ], style={"marginTop": "20px"})
    
    if trivia_game.is_game_over:
        # Show game over screen with final score
        questions_answered = trivia_game.current_question_index
        max_possible = min(10, len(trivia_game.questions))
        
        return dbc.Card([
            dbc.CardHeader(html.H4("Trivia Game - Game Over!", className="card-title")),
            dbc.CardBody([
                html.Div([
                    html.H3(f"Game Over!", style={"color": "white", "textAlign": "center"}),
                    html.H4(f"Your final score: {trivia_game.score} out of {questions_answered}", 
                           style={"color": "white", "textAlign": "center", "marginBottom": "20px"}),
                    html.Div([
                        html.H5(f"Total Questions Answered: {questions_answered}", style={"color": "white"}),
                        html.H5(f"Correct Answers: {trivia_game.score}", style={"color": "green"}),
                        html.H5(f"Mistakes Made: {trivia_game.mistakes}", style={"color": "red"})
                    ], style={"margin": "0 auto", "width": "fit-content", "textAlign": "left"}),
                    html.Hr(),
                    html.P("Select another movie or refresh this movie to play again!", 
                          style={"color": "white", "textAlign": "center"})
                ])
            ])
        ], style={"marginTop": "20px"})
    
    # Get current question before making any changes
    current_q = trivia_game.get_current_question()
    if not current_q:
        return dbc.Card([
            dbc.CardHeader(html.H4("Trivia Game", className="card-title")),
            dbc.CardBody([
                html.H5("No questions available for this movie. Try another movie.", 
                       style={"color": "black", "textAlign": "center"})
            ])
        ], style={"marginTop": "20px"})
        
    # Format the current question for display
    options = []
    for i in range(4):
        option_key = chr(65 + i)  # A, B, C, D
        option_value = current_q['options'].get(option_key, f"Option {option_key}")
        options.append((option_key, option_value))
    
    # Use the current round from the trivia game object
    current_round = trivia_game.round_number
    total_rounds = 10  
    
    print(f"Showing trivia question: Round {current_round}/{total_rounds}, Score: {trivia_game.score}, Mistakes: {trivia_game.mistakes}")
    
    return dbc.Card([
        dbc.CardHeader(html.H4("Trivia Game", className="card-title")),
        dbc.CardBody([
            # Game status header - shows score, round, and mistakes in a row of three cards
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("SCORE", style={"color": "white", "textAlign": "center", "marginBottom": "5px", "fontSize": "14px"}),
                            html.H3(f"{trivia_game.score}", style={"color": "white", "textAlign": "center", "fontWeight": "bold"})
                        ], style={"padding": "10px"})
                    ], style={"backgroundColor": "#4CAF50", "border": "none", "borderRadius": "8px"})
                ], width=4),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("QUESTION", style={"color": "white", "textAlign": "center", "marginBottom": "5px", "fontSize": "14px"}),
                            html.H3(f"{current_round}/{total_rounds}", style={"color": "white", "textAlign": "center", "fontWeight": "bold"})
                        ], style={"padding": "10px"})
                    ], style={"backgroundColor": "#2196F3", "border": "none", "borderRadius": "8px"})
                ], width=4),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("MISTAKES", style={"color": "white", "textAlign": "center", "marginBottom": "5px", "fontSize": "14px"}),
                            html.H3(f"{trivia_game.mistakes}/3", style={"color": "white", "textAlign": "center", "fontWeight": "bold"})
                        ], style={"padding": "10px"})
                    ], style={"backgroundColor": "#FF5722" if trivia_game.mistakes > 0 else "#9E9E9E", "border": "none", "borderRadius": "8px"})
                ], width=4)
            ], className="mb-4"),
            
            dbc.Card([
                dbc.CardBody([
                    html.H4(current_q['question'], 
                           style={"color": "white", "textAlign": "center", "marginBottom": "10px", "fontWeight": "bold"})
                ], style={"padding": "20px", "backgroundColor": "#2C2C2C"})
            ], className="mb-4", style={"borderRadius": "10px"}),
            
            dbc.Row([
                dbc.Col([
                    html.Div([
                        dbc.Button(
                            f"{options[i][0]}. {options[i][1]}",
                            id={'type': 'answer_btn', 'index': i},
                            color="primary",
                            className="mb-3",
                            style={
                                "backgroundColor": website_theme["button-color"],
                                "color": website_theme["button-text-color"],
                                "borderColor": website_theme["button-color"],
                                "width": "100%",
                                "textAlign": "left",
                                "padding": "15px",
                                "borderRadius": "8px",
                                "boxShadow": "0px 3px 5px rgba(0,0,0,0.2)"
                            }
                        ) for i in range(4)
                    ])
                ], width={"size": 10, "offset": 1})
            ])
        ], style={"padding": "20px"})
    ], style={"marginTop": "20px", "borderRadius": "12px", "overflow": "hidden", "boxShadow": "0 4px 8px rgba(0,0,0,0.1)"})

def create_recommended_tab(media_id, media_type):
    recommendations = api_helpers.get_recommended_content(media_id, media_type)
    
    recommended_cards = []
    for rec in recommendations:
        card = dbc.Card([
            dbc.CardImg(src=rec['poster'], top=True),
            dbc.CardBody([
                html.H5(rec['title'], className="card-title")
            ])
        ], style={'width': '18rem', 'margin': '10px', 'cursor': 'pointer'})
        recommended_cards.append(card)
    
    return dbc.Card([
        dbc.CardHeader("🎬 Recommended Movies"),
        dbc.CardBody([
            dbc.Row(recommended_cards),
            html.Div(id='recommendation_details')
        ])
    ])

@app.callback(
    Output('recommendation_details', 'children'),
    [Input(f"recommend-{i}", 'n_clicks') for i in range(1, 7)]
)
def show_recommendation_details(*args):
    ctx = dash.callback_context
    if not ctx.triggered:
        return None
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if not button_id.startswith('recommend-'):
        return None
    
    rec_id = int(button_id.split('-')[1])
    movie_info = api_helpers.get_comprehensive_media_info(rec_id, 'movie')
    
    return dbc.Card([
        dbc.CardHeader(movie_info['title']),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Img(
                        src=movie_info['poster'], 
                        style={'max-width': '300px', 'height': 'auto'}
                    )
                ], width=4),
                dbc.Col([
                    html.H4("Overview"),
                    html.P(movie_info['overview']),
                    
                    html.H5("Details"),
                    html.P(f"Genres: {', '.join(movie_info['genres'])}"),
                    html.P(f"Release Date: {movie_info['release_date']}"),
                    html.P(f"Runtime: {movie_info['runtime']} minutes"),
                    html.P(f"Rating: {movie_info['rating']}/10"),
                    
                    html.H5("Directors"),
                    html.P(", ".join(movie_info['directors'])),
                    
                    html.H5("Top Cast"),
                    html.Ul([html.Li(cast) for cast in movie_info['top_cast']]),
                    
                    html.H5("Reviews"),
                    html.Ul([html.Li(review) for review in movie_info['reviews']])
                ], width=8)
            ])
        ])
    ])

@app.callback(
    Output('selected_recipes_container', 'children'),
    [Input('snacks_recipe_dropdown', 'value'),
     Input('main_course_recipe_dropdown', 'value'),
     Input('dessert_recipe_dropdown', 'value')]
)
def update_selected_recipes(snacks_value, main_course_value, dessert_value):
    selected_recipes = []
    for value in [snacks_value, main_course_value, dessert_value]:
        if value and value != 'none':
            recipe = json.loads(value)
            recipe_details = api_helpers.get_detailed_recipe(recipe['id'])
            
            instructions = recipe_details['instructions'].split('.')
            instructions = [step.strip() for step in instructions if step.strip()]
            
            recipe_content = f"""Recipe: {recipe_details['title']}

Ingredients:
{chr(10).join(recipe_details['ingredients'])}

Instructions:
{chr(10).join(instructions)}
"""
            download_file = base64.b64encode(recipe_content.encode()).decode()
            download_href = f"data:text/plain;base64,{download_file}"
            
            selected_recipes.append(
                dbc.Card([
                    dbc.CardHeader(recipe['title']),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Img(
                                    src=recipe_details['image'],
                                    style={'width': '200px', 'height': 'auto', 'object-fit': 'cover'}
                                )
                            ], width=4),
                            dbc.Col([
                                html.H5("Ingredients"),
                                html.Ul([html.Li(ing) for ing in recipe_details['ingredients']]),
                                
                                html.H5("Instructions"),
                                html.Ol([html.Li(step) for step in instructions if step.strip()]),
                                
                        html.A(
                                    dbc.Button(
                                        "Download Recipe",
                                        color="primary",
                                        className="mt-2",
                                        style={
                                            "backgroundColor": website_theme["button-text-color"],
                                            "color": website_theme["button-color"],
                                            "borderColor": website_theme["button-text-color"]
                                        }
                                    ),
                                    href=download_href,
                                    download=f"{recipe['title'].replace(' ', '_')}_recipe.txt"
                                )
                            ], width=8)
                        ])
                    ])
                ], className="mb-4")
            )
    
    return selected_recipes

@app.callback(
    Output('recipe_details_container', 'children'),
    [Input('snacks_recipe_dropdown', 'value'),
     Input('main_course_recipe_dropdown', 'value'),
     Input('dessert_recipe_dropdown', 'value')]
)
def update_recipe_details(snacks_value, main_course_value, dessert_value):
    ctx = dash.callback_context
    if not ctx.triggered:
        return None
    
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    recipe_data = ctx.triggered[0]['value']
    
    if not recipe_data or recipe_data == 'none':
        return None

    return None

@app.callback(
    Output('grocery_list_container', 'children'),
    [Input('snacks_recipe_dropdown', 'value'),
     Input('main_course_recipe_dropdown', 'value'),
     Input('dessert_recipe_dropdown', 'value')]
)
def generate_grocery_list(snacks_value, main_course_value, dessert_value):
    # Check if any recipes are selected
    selected_values = [val for val in [snacks_value, main_course_value, dessert_value] 
                      if val and val != 'none']
    
    if not selected_values:
        return None
        
    all_ingredients = {}
    recipes = []
    
    for value in selected_values:
        recipe_info = json.loads(value)
        recipe_details = api_helpers.get_detailed_recipe(recipe_info['id'])
        recipes.append(recipe_details)
        
        # Add each ingredient to the list
        for ing in recipe_details['ingredients']:
            # Simple parsing to estimate amounts
            parts = ing.split(' ', 2)
            if len(parts) >= 2 and parts[0].replace('.', '', 1).isdigit():
                try:
                    amount = float(parts[0])
                    unit = parts[1]
                    name = parts[2] if len(parts) > 2 else unit
                    
                    # Create a key without the amount for deduplication
                    key = name.lower().strip()
                    if key in all_ingredients:
                        all_ingredients[key]['amount'] += amount
                    else:
                        all_ingredients[key] = {
                            'name': name,
                            'amount': amount,
                            'unit': unit,
                            'original': float(amount)  # Store original amount for scaling
                        }
                except (ValueError, IndexError):
                    # Fallback for ingredients that can't be parsed
                    if ing in all_ingredients:
                        all_ingredients[ing] = {
                            'name': ing,
                            'amount': 'as needed',
                            'unit': ''
                        }
                    else:
                        all_ingredients[ing] = {
                            'name': ing,
                            'amount': 'as needed',
                            'unit': ''
                        }
            else:
                # For ingredients without clear amounts
                all_ingredients[ing] = {
                    'name': ing,
                    'amount': 'as needed',
                    'unit': ''
                }
    
    # Calculate servings
    total_original_servings = sum(int(recipe.get('servings', 1)) for recipe in recipes)
    if total_original_servings == 0:
        total_original_servings = 1  # Avoid division by zero
    
    # Create a function to update grocery list based on desired servings
    def update_grocery_list(desired_servings):
        # Calculate scaling factor
        scaling_factor = desired_servings / total_original_servings
        
        # Scale ingredients
        scaled_ingredients = {}
        for key, ing_data in all_ingredients.items():
            scaled_ing = ing_data.copy()
            if isinstance(ing_data['amount'], (int, float)) and 'original' in ing_data:
                scaled_ing['amount'] = round(ing_data['original'] * scaling_factor, 2)
            scaled_ingredients[key] = scaled_ing
        
        # Create a table for the grocery list
        table_header = html.Thead(html.Tr([
            html.Th("Ingredient", style={"width": "70%", "color": "white"}),
            html.Th("Amount", style={"width": "30%", "color": "white"})
        ]))
        
        rows = []
        for ing_data in scaled_ingredients.values():
            amount_text = f"{ing_data['amount']} {ing_data['unit']}" if isinstance(ing_data['amount'], (int, float)) else ing_data['amount']
            rows.append(html.Tr([
                html.Td(ing_data['name'], style={"color": "white"}),
                html.Td(amount_text, style={"color": "white"})
            ]))
        
        table_body = html.Tbody(rows)
        
        # Create a downloadable grocery list
        grocery_content = f"Grocery List (for {desired_servings} servings):\n\n"
        for ing_data in scaled_ingredients.values():
            amount_text = f"{ing_data['amount']} {ing_data['unit']}" if isinstance(ing_data['amount'], (int, float)) else ing_data['amount']
            grocery_content += f"{ing_data['name']}: {amount_text}\n"
            
        download_file = base64.b64encode(grocery_content.encode()).decode()
        download_href = f"data:text/plain;base64,{download_file}"
        
        return dbc.Table([table_header, table_body], bordered=True, hover=True, className="mb-3", 
                        style={"backgroundColor": "#343a40", "borderColor": "#495057"}), download_href

    # Generate initial grocery table with original servings
    grocery_table, download_href = update_grocery_list(total_original_servings)
    
    # Create component with servings input
    return dbc.Card([
        dbc.CardHeader("🛒 Grocery List"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.H5("Adjust servings:", style={"color": "white", "marginBottom": "10px"}),
                    dbc.InputGroup([
                        dbc.InputGroupText("Servings:", style={"backgroundColor": "#495057", "color": "white"}),
                        dbc.Input(
                            id="servings_input",
                            type="number",
                            value=total_original_servings,
                            min=1,
                            step=1,
                            style={"color": "black"}
                        ),
                        dbc.Button(
                            "Update",
                            id="update_servings_btn",
                            color="primary",
                            style={
                                "backgroundColor": website_theme["button-color"],
                                "color": website_theme["button-text-color"],
                                "borderColor": website_theme["button-color"]
                            }
                        )
                    ], className="mb-3"),
                    html.Div(id="current_servings", children=[
                        html.H5(f"Current recipe(s) make: {total_original_servings} servings", 
                               style={"marginBottom": "15px", "color": "white"})
                    ]),
                    html.Div(id="grocery_table_container", children=[grocery_table]),
                    html.A(
                        dbc.Button(
                            "Download Grocery List", 
                            color="success", 
                            className="mt-2",
                            style={
                                "backgroundColor": website_theme["button-text-color"],
                                "color": website_theme["button-color"],
                                "borderColor": website_theme["button-text-color"]
                            }
                        ),
                        id="download_grocery_link",
                        href=download_href,
                        download="grocery_list.txt"
                    )
                ], width=12)
            ])
        ])
    ])

# Add callback to update grocery list when servings change
@app.callback(
    [Output('grocery_table_container', 'children'),
     Output('download_grocery_link', 'href'),
     Output('current_servings', 'children')],
    [Input('update_servings_btn', 'n_clicks')],
    [State('servings_input', 'value'),
     State('snacks_recipe_dropdown', 'value'),
     State('main_course_recipe_dropdown', 'value'),
     State('dessert_recipe_dropdown', 'value')]
)
def update_grocery_servings(n_clicks, desired_servings, snacks_value, main_course_value, dessert_value):
    if not n_clicks or not desired_servings:
        raise dash.exceptions.PreventUpdate
    
    # Set a minimum of 1 serving
    desired_servings = max(1, int(desired_servings))
    
    # Get selected recipes
    selected_values = [val for val in [snacks_value, main_course_value, dessert_value] 
                      if val and val != 'none']
    
    if not selected_values:
        return dash.no_update, dash.no_update, dash.no_update
    
    # Process ingredients
    all_ingredients = {}
    recipes = []
    
    for value in selected_values:
        recipe_info = json.loads(value)
        recipe_details = api_helpers.get_detailed_recipe(recipe_info['id'])
        recipes.append(recipe_details)
        
        for ing in recipe_details['ingredients']:
            parts = ing.split(' ', 2)
            if len(parts) >= 2 and parts[0].replace('.', '', 1).isdigit():
                try:
                    amount = float(parts[0])
                    unit = parts[1]
                    name = parts[2] if len(parts) > 2 else unit
                    
                    key = name.lower().strip()
                    if key in all_ingredients:
                        all_ingredients[key]['amount'] += amount
                    else:
                        all_ingredients[key] = {
                            'name': name,
                            'amount': amount,
                            'unit': unit,
                            'original': float(amount)
                        }
                except (ValueError, IndexError):
                    if ing not in all_ingredients:
                        all_ingredients[ing] = {
                            'name': ing,
                            'amount': 'as needed',
                            'unit': ''
                        }
            else:
                if ing not in all_ingredients:
                    all_ingredients[ing] = {
                        'name': ing,
                        'amount': 'as needed',
                        'unit': ''
                    }
    
    # Calculate original servings
    total_original_servings = sum(int(recipe.get('servings', 1)) for recipe in recipes)
    if total_original_servings == 0:
        total_original_servings = 1
    
    # Calculate scaling factor
    scaling_factor = desired_servings / total_original_servings
    
    # Scale ingredients
    for key, ing_data in all_ingredients.items():
        if isinstance(ing_data['amount'], (int, float)) and 'original' in ing_data:
            all_ingredients[key]['amount'] = round(ing_data['original'] * scaling_factor, 2)
    
    # Create the table
    table_header = html.Thead(html.Tr([
        html.Th("Ingredient", style={"width": "70%", "color": "white"}),
        html.Th("Amount", style={"width": "30%", "color": "white"})
    ]))
    
    rows = []
    for ing_data in all_ingredients.values():
        amount_text = f"{ing_data['amount']} {ing_data['unit']}" if isinstance(ing_data['amount'], (int, float)) else ing_data['amount']
        rows.append(html.Tr([
            html.Td(ing_data['name'], style={"color": "white"}),
            html.Td(amount_text, style={"color": "white"})
        ]))
    
    table_body = html.Tbody(rows)
    
    # Create a downloadable grocery list
    grocery_content = f"Grocery List (for {desired_servings} servings):\n\n"
    for ing_data in all_ingredients.values():
        amount_text = f"{ing_data['amount']} {ing_data['unit']}" if isinstance(ing_data['amount'], (int, float)) else ing_data['amount']
        grocery_content += f"{ing_data['name']}: {amount_text}\n"
        
    download_file = base64.b64encode(grocery_content.encode()).decode()
    download_href = f"data:text/plain;base64,{download_file}"
    
    # Update the servings display
    servings_display = html.H5(
        f"Adjusted to: {desired_servings} servings (original: {total_original_servings})", 
        style={"marginBottom": "15px", "color": "white"}
    )
    
    # Return the updated table, download link, and servings display
    return (
        dbc.Table([table_header, table_body], bordered=True, hover=True, className="mb-3", 
                  style={"backgroundColor": "#343a40", "borderColor": "#495057"}),
        download_href,
        servings_display
    )

@app.callback(
    Output('movie_chat_messages', 'children'),
    [Input('movie_chat_send', 'n_clicks'),
     Input('movie_chat_input', 'n_submit')],
    [State('movie_chat_input', 'value'),
     State('movie_selection_dropdown', 'value'),
     State('movie_chat_messages', 'children')]
)
def movie_chat_assistant(n_clicks, n_submit, chat_input, selected_movie, current_messages):
    if not (n_clicks or n_submit) or not selected_movie or not chat_input:
        return current_messages or []
    
    try:
        # Parse selected movie details
        movie_info = json.loads(selected_movie)
        current_media = api_helpers.get_comprehensive_media_info(movie_info['id'], movie_info['media_type'])
        
        # Prepare Cohere prompt
        prompt = f"""You are a movie expert assistant. 
        Movie/Show Details:
        Title: {current_media['title']}
        Overview: {current_media['overview']}
        Genre: {', '.join(current_media['genres'])}
        Cast: {', '.join(current_media['top_cast'])}
        Directors: {', '.join(current_media['directors'])}

        User Question: {chat_input}
        
        Provide a helpful, concise, and informative response."""
        
        try:
            response = api_helpers.cohere_client.generate(
                model='command',
                prompt=prompt,
                max_tokens=200,
                temperature=0.7
            )
            assistant_response = response.generations[0].text
            
            # Create chat messages
            messages = current_messages or []
            messages.extend([
                html.Div([
                    html.Div(chat_input, className="user-message mb-2 p-2 bg-primary text-white rounded", style={'max-width': '80%', 'margin-left': 'auto'}),
                    html.Div(assistant_response, className="assistant-message mb-2 p-2 bg-light rounded", style={'max-width': '80%'})
                ])
            ])
            
            return messages
        except Exception as e:
            error_message = f"Error generating response: {str(e)}"
            messages = current_messages or []
            messages.append(html.Div(error_message, className="error-message text-danger"))
            return messages
    except Exception as e:
        error_message = f"Error processing movie information: {str(e)}"
        messages = current_messages or []
        messages.append(html.Div(error_message, className="error-message text-danger"))
        return messages

@app.callback(
    Output('main_tabs', 'active_tab'),
    [Input({'type': 'nav_btn', 'tab': ALL}, 'n_clicks')],
    prevent_initial_call=True
)
def navigate_to_tab(btn_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        return 'overview_tab'
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    try:
        button_data = json.loads(button_id)
        return button_data['tab']
    except:
        return 'overview_tab'

# Add a separate callback for trivia answer buttons
@app.callback(
    Output('tab_content', 'children', allow_duplicate=True),
    [Input({'type': 'answer_btn', 'index': i}, 'n_clicks') for i in range(4)],
    [State('main_tabs', 'active_tab'),
     State('movie_selection_dropdown', 'value')],
    prevent_initial_call=True
)
def handle_trivia_answers(*args):
    global CURRENT_TRIVIA_GAME
    
    answer_clicks = args[:4]  # First 4 args are the button clicks
    active_tab = args[4]      # 5th arg is the active tab
    selected_movie = args[5]  # 6th arg is the selected movie
    
    if not selected_movie or active_tab != 'trivia_tab':
        return dash.no_update
    
    try:
        movie_info = json.loads(selected_movie)
        ctx = dash.callback_context
        
        if ctx.triggered:
            button_id = ctx.triggered[0]['prop_id'].split('.')[0]
            if isinstance(button_id, str):
                try:
                    # Extract the button index from the dictionary ID
                    button_data = json.loads(button_id)
                    if button_data['type'] == 'answer_btn':
                        option_index = button_data['index']  # Already 0-based index
                        
                        print(f"Button pressed with index {option_index}")
                        
                        # Initialize new game if needed
                        if not CURRENT_TRIVIA_GAME:
                            print("Creating new trivia game in answer handler")
                            CURRENT_TRIVIA_GAME = TriviaGame(movie_info, api_helpers.cohere_client)
                            # Ensure game state is explicitly set
                            CURRENT_TRIVIA_GAME.current_question_index = 0
                            CURRENT_TRIVIA_GAME.score = 0
                            CURRENT_TRIVIA_GAME.mistakes = 0
                            CURRENT_TRIVIA_GAME.round_number = 1
                            CURRENT_TRIVIA_GAME.is_game_over = False
                        
                        # Check the answer and update game state
                        result = CURRENT_TRIVIA_GAME.check_answer(option_index)
                        
                        print(f"Answer result: {result}")
                        print(f"Game state after answer: index={CURRENT_TRIVIA_GAME.current_question_index}, round={CURRENT_TRIVIA_GAME.round_number}, score={CURRENT_TRIVIA_GAME.score}, mistakes={CURRENT_TRIVIA_GAME.mistakes}")
                        
                        # Return updated trivia tab
                        return create_trivia_tab(CURRENT_TRIVIA_GAME)
                except Exception as e:
                    print(f"Error handling trivia answer: {e}")
                    import traceback
                    traceback.print_exc()
        
        return dash.no_update
    except Exception as e:
        print(f"Exception in handle_trivia_answers: {e}")
        import traceback
        traceback.print_exc()
        return dash.no_update

# Helper functions for tab creation
def create_navigation_buttons(current_tab):
    """Create navigation buttons based on the current tab"""
    buttons = []
    
    button_style = {
        "backgroundColor": website_theme["button-color"],
        "color": website_theme["button-text-color"],
        "borderColor": website_theme["button-color"]
    }
    
    # Define all possible buttons with dictionary IDs
    all_buttons = {
        'overview_tab': dbc.Button("Know more about the movie", 
                                 id={'type': 'nav_btn', 'tab': 'overview_tab'}, 
                                 color="primary", 
                                 className="me-2", 
                                 style=button_style),
        'meal_tab': dbc.Button("Check out best meal pairings", 
                              id={'type': 'nav_btn', 'tab': 'meal_tab'}, 
                              color="primary", 
                              className="me-2", 
                              style=button_style),
        'trivia_tab': dbc.Button("Play a trivia game", 
                                id={'type': 'nav_btn', 'tab': 'trivia_tab'}, 
                                color="primary", 
                                className="me-2", 
                                style=button_style),
        'recommended_tab': dbc.Button("Explore similar movies", 
                                    id={'type': 'nav_btn', 'tab': 'recommended_tab'}, 
                                    color="primary", 
                                    style=button_style)
    }
    
    # Show only buttons for tabs other than current tab
    for tab_id, button in all_buttons.items():
        if tab_id != current_tab:
            buttons.append(button)
    
    return html.Div([
        dbc.Row([
            dbc.Col(buttons, className="d-flex justify-content-center mt-4")
        ])
    ])

# Add new helper function for dish recommendations
def get_dish_recommendations(media_details):
    """Generate dish recommendations based on media details"""
    genre = media_details.get('genres', ['Drama'])[0]
    title = media_details.get('title', '')
    
    genre_recommendations = {
        'Action': "For action movies, we recommend hearty, protein-rich foods like steak, burgers, or loaded nachos that will fuel your adrenaline!",
        'Comedy': "Light, fun finger foods work well with comedies - try a variety of tapas, mini sliders, or a colorful charcuterie board.",
        'Drama': "Dramatic films pair well with sophisticated comfort foods like pasta dishes, risotto, or a well-crafted cheese board.",
        'Horror': "Dark, intense foods complement horror films - try a blood-red pasta, blackened chicken, or dark chocolate desserts.",
        'Romance': "Romantic movies call for sensual foods like chocolate-covered strawberries, champagne, and elegant seafood dishes.",
        'Science Fiction': "For sci-fi, try futuristic presentations - colorful foods with unexpected combinations or molecular gastronomy-inspired dishes.",
        'Adventure': "Adventure films pair well with exotic cuisine from the regions featured in the movie - tacos, curries, or Mediterranean dishes.",
        'Fantasy': "Magical, whimsical dishes work with fantasy - try colorful foods, themed cupcakes, or elaborate desserts.",
        'Animation': "Fun, colorful foods that appeal to all ages - bright fruit platters, themed cookies, or creative sushi rolls.",
        'Thriller': "Intense, spicy foods match the tension in thrillers - try fiery curries, bold flavors, and dark beverages.",
        'Documentary': "Authentic cuisine related to the documentary's subject matter or healthy, mindful food choices.",
        'Family': "Crowd-pleasing classics that everyone can enjoy - pizza, pasta bars, or build-your-own taco stations."
    }
    
    # Default recommendation if genre not found
    recommendation = genre_recommendations.get(genre, "We recommend exploring international cuisines like Italian pasta, Asian stir-fry, or Mediterranean platters that everyone can enjoy.")
    
    # Add personalized touch
    return f"Based on '{title}', {recommendation} Consider pairing with themed drinks that match the movie's mood!"

if __name__ == "__main__":
    app.run(debug=True)