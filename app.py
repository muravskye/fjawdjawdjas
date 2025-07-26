from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from apify_client import ApifyClient
import time
import os
import json
import requests # Used for making HTTP requests to external APIs
import re # Import re for regex operations
from datetime import datetime # Import datetime for timestamping logs

app = Flask(__name__)
# Set a secret key for session management. CHANGE THIS IN PRODUCTION!
app.secret_key = os.urandom(24)

# Your API Keys (LOAD FROM ENVIRONMENT VARIABLES IN PRODUCTION!)
# It's highly recommended to load these from environment variables (e.g., os.environ.get("APIFY_API_TOKEN"))
# instead of hardcoding them, especially for production.
APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN") # Replace with your Apify API token
# Note: The provided key format 'sk-proj-...' is typically for Google Gemini.
# If you intend to use OpenAI, please ensure you have a valid OpenAI API key.
# The code targets the OpenAI endpoint, assuming you will use an OpenAI key.
AI_API_KEY = os.environ.get("AI_API_KEY")

# Number of recent posts to scrape for the profile
NUM_POSTS_TO_SCRAPE = 5
# Number of comments to fetch for each post using the dedicated comment scraper
NUM_COMMENTS_TO_FETCH_PER_POST = 5

# Path to the saved profiles JSON file
SAVED_PROFILES_FILE = 'saved_profiles.json'
# Path to the raw Apify logs file
APIFY_RAW_LOG_FILE = 'apify_raw_logs.jsonl' # .jsonl for JSON Lines format

def load_saved_profiles():
    """Loads saved profile data from a JSON file."""
    if os.path.exists(SAVED_PROFILES_FILE):
        with open(SAVED_PROFILES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_profile_data(username, data):
    """Saves a profile's analysis data to the JSON file."""
    saved_profiles = load_saved_profiles()
    saved_profiles[username] = data
    with open(SAVED_PROFILES_FILE, 'w') as f:
        json.dump(saved_profiles, f, indent=4)
    print(f"Server: Profile data for {username} saved to {SAVED_PROFILES_FILE}")

def log_apify_raw_data(username, data):
    """Appends raw Apify data to a JSONL log file."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "username": username,
        "data": data
    }
    try:
        with open(APIFY_RAW_LOG_FILE, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
        print(f"Server: Raw Apify data for {username} logged to {APIFY_RAW_LOG_FILE}")
    except Exception as e:
        print(f"Server: Error writing raw Apify data to log file: {e}")


def scrape_instagram_profile_and_comments(username):
    """
    Scrapes an Instagram profile and its recent posts with comments using Apify.
    Returns a dictionary of scraped data or None on failure.
    """
    client = ApifyClient(APIFY_API_TOKEN)
    scraped_data = {
        "profile": {},
        "latestPosts": []
    }

    print(f"Server: ▶ Scraping profile: {username} with {NUM_POSTS_TO_SCRAPE} recent posts...")
    try:
        # 1. Scrape Profile and Post Metadata
        profile_input = {
            "usernames": [username],
            "resultsLimit": 1,
            "resultsType": "full",
            "resultsLimitPerProfile": NUM_POSTS_TO_SCRAPE,
            "scrapePosts": True,
            "scrapePostsLikes": True,
            "scrapePostsComments": False, # We'll get comments with a dedicated scraper
            "shouldDownloadVideos": False
        }
        run_profile = client.actor("apify/instagram-profile-scraper").call(run_input=profile_input)
        profile_dataset_items = list(client.dataset(run_profile["defaultDatasetId"]).iterate_items())

        if not profile_dataset_items:
            print(f"Server: ⚠ No profile data found for {username} or profile is private.")
            return None

        profile_data = profile_dataset_items[0]
        # --- NEW: Print raw profile_data to terminal and log to file ---
        print(f"Server: Raw profile data from Apify for {username}: {json.dumps(profile_data, indent=2)}")
        log_apify_raw_data(username, profile_data)
        # --- END NEW ---

        scraped_data["profile"] = {
            "username": profile_data.get('username'),
            "fullName": profile_data.get('fullName'),
            "followersCount": int(profile_data.get('followersCount', 0) or 0), # Explicitly convert to int
            "followsCount": int(profile_data.get('followsCount', 0) or 0),     # Explicitly convert to int
            "bio": profile_data.get('biography'), # Changed from 'bio' to 'biography'
            # Ensure profilePicUrl is always a valid string, defaulting to a placeholder
            "profilePicUrl": profile_data.get('profilePicUrl') or 'https://placehold.co/150x150/FF69B4/FFFFFF?text=Profile+Pic',
            "profileUrl": f"https://www.instagram.com/{profile_data.get('username')}/",
        }

        posts = profile_data.get("latestPosts", [])
        scraped_data["latestPosts"] = []

        # 2. Scrape Comments for Each Post (if posts exist)
        if posts:
            for post_index, post in enumerate(posts[:NUM_POSTS_TO_SCRAPE]):
                post_shortcode = post.get('shortCode')
                if post_shortcode:
                    post_url = f"https://www.instagram.com/p/{post_shortcode}/"
                    print(f"Server: ▶ Gathering {NUM_COMMENTS_TO_FETCH_PER_POST} interactions for Post {post_index + 1}: {post_url}...")

                    comments_input = {
                        "directUrls": [post_url],
                        "resultsLimit": NUM_COMMENTS_TO_FETCH_PER_POST
                    }
                    run_comments = client.actor("apify/instagram-comment-scraper").call(run_input=comments_input)
                    comments_dataset_items = list(client.dataset(run_comments["defaultDatasetId"]).iterate_items())

                    # Add comments to the post object
                    post_copy = post.copy() # Avoid modifying original post object from Apify client directly
                    post_copy["comments"] = comments_dataset_items
                    # Extract hashtags from caption if not directly provided by profile scraper
                    post_copy["hashtags"] = [tag.strip("#") for tag in post_copy.get('caption', '').split() if tag.startswith('#')]
                    # Ensure likesCount and commentsCount are defaulted to 0 and explicitly converted to int
                    post_copy["likesCount"] = int(post_copy.get('likesCount', 0) or 0)
                    post_copy["commentsCount"] = int(post_copy.get('commentsCount', 0) or 0)
                    scraped_data["latestPosts"].append(post_copy)
                else:
                    print(f"Server: Could not get shortcode for Post {post_index + 1} to gather interactions.")
                    # Still add the post, but without detailed comments
                    post_copy = post.copy()
                    post_copy["comments"] = []
                    post_copy["hashtags"] = [tag.strip("#") for tag in post_copy.get('caption', '').split() if tag.startswith('#')]
                    post_copy["likesCount"] = int(post_copy.get('likesCount', 0) or 0)
                    post_copy["commentsCount"] = int(post_copy.get('commentsCount', 0) or 0)
                    scraped_data["latestPosts"].append(post_copy)
        else:
            print(f"Server: No recent content found for {username}.")

        return scraped_data

    except Exception as e:
        print(f"Server: An error occurred during data retrieval: {e}")
        return None

def get_ai_analysis(data):
    """
    Constructs a prompt and calls the OpenAI API for analysis.
    Returns a dictionary with 'text' and 'score'.
    """
    print("Server: Constructing prompt for AI analysis.")
    prompt = f"""Analyze the following Instagram profile data and provide a concise opinion.
    Your analysis must include both strengths and weaknesses/areas for improvement.
    At the very beginning of your response, provide an "Overall Score: X/10", where X is an integer from 1 to 10.
    Keep the analysis to a maximum of 150 words.

    Profile Username: {data['profile']['username']}
    Full Name: {data['profile']['fullName']}
    Followers: {data['profile']['followersCount']}
    Following: {data['profile']['followsCount']}
    Bio: {data['profile']['bio'] or 'Not provided'}

    Recent Posts (summarized by caption, hashtags, and first comment if available):
    """

    for index, post in enumerate(data['latestPosts']):
        caption_preview = (post['caption'][:100] + '...') if post['caption'] else 'No caption'
        hashtags = f" #{' #'.join(post['hashtags'])}" if post['hashtags'] else ''
        prompt += f"\n- Content {index + 1} (Likes: {post['likesCount']}, Interactions Count: {post['commentsCount']}): \"{caption_preview}{hashtags}\""
        if post['comments'] and len(post['comments']) > 0:
            # Safely access 'text' key, providing a default if it doesn't exist
            first_comment_text = post['comments'][0].get('text', 'No text available for interaction')
            first_comment_preview = (first_comment_text[:50] + '...') if first_comment_text else 'No text'
            prompt += f" First interaction: \"{first_comment_preview}\""

    analysis_text = "AI analysis could not be generated."
    overall_score = 0

    print("Server: Sending request to AI API (OpenAI endpoint)...")
    try:
        payload = {
            "model": "gpt-3.5-turbo", # Or "gpt-4o"
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200
        }

        api_url = "https://api.openai.com/v1/chat/completions" # OpenAI Chat Completions endpoint
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {AI_API_KEY}'
        }

        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        result = response.json()

        print("Server: AI API raw response:", result)

        if result.get('choices') and len(result['choices']) > 0 and \
           result['choices'][0].get('message') and result['choices'][0]['message'].get('content'):
            analysis_text = result['choices'][0]['message']['content']

            # Extract overall score using regex
            score_match = re.search(r"Overall Score:\s*(\d+)\/10", analysis_text)
            if score_match:
                overall_score = int(score_match.group(1))
                overall_score = max(1, min(10, overall_score)) # Ensure score is within 1-10

        else:
            print("Server: Unexpected AI API response structure or no choices:", result)
            if result.get('error') and result['error'].get('message'):
                analysis_text = f"AI analysis failed: {result['error']['message']}"
            else:
                analysis_text = "AI analysis could not be generated due to unexpected response structure or no content."

    except requests.exceptions.RequestException as e:
        print(f"Server: Error calling AI API: {e}")
        analysis_text = f"Failed to get AI analysis due to a network or API call error: {e}"
    except Exception as e:
        print(f"Server: An unexpected error occurred during AI analysis: {e}")
        analysis_text = f"An unexpected error occurred during AI analysis: {e}"

    return {"text": analysis_text, "score": overall_score}


@app.route('/')
def index():
    """Renders the initial input page."""
    # Retrieve any error message from session to display on the index page
    error_message = session.pop('error_message', None)
    return render_template('index.html', error_message=error_message)

@app.route('/analyze', methods=['POST'])
def analyze():
    """
    Handles the analysis request, stores the username in session,
    and redirects to the loading page.
    """
    username = request.form.get('username')
    if not username:
        session['error_message'] = "Please enter an Instagram username."
        return redirect(url_for('index'))

    session['username_to_analyze'] = username # Store username for lookup later
    session.pop('error_message', None) # Clear any previous error message
    return redirect(url_for('loading'))

@app.route('/loading')
def loading():
    """Renders the loading screen."""
    return render_template('loading.html')

@app.route('/perform_analysis')
def perform_analysis():
    """
    Performs the real scraping and AI analysis in the background.
    This is called via AJAX from the loading page.
    """
    username = session.get('username_to_analyze')
    if not username:
        return jsonify({"status": "error", "message": "No username in session."}), 400

    saved_profiles = load_saved_profiles()
    if username in saved_profiles:
        print(f"Server: Profile data for {username} found in saved_profiles.json. Using cached data.")
        # No need to store in session, as results page will load directly from file
        return jsonify({"status": "complete", "message": "Analysis complete (cached)."})

    print(f"Server: Starting analysis for username: {username}")
    time.sleep(1) # Simulate initial processing time

    # Perform real Instagram scraping
    scraped_data = scrape_instagram_profile_and_comments(username)

    if not scraped_data:
        session['error_message'] = "Failed to retrieve Instagram data. Profile might be private or non-existent."
        return jsonify({"status": "error", "message": "Data retrieval failed."}), 500

    # Perform AI analysis
    ai_analysis_result = get_ai_analysis(scraped_data)

    # Combine all data to save
    full_analysis_data = {
        "profile_data": scraped_data,
        "ai_analysis": ai_analysis_result
    }
    save_profile_data(username, full_analysis_data)

    print(f"Server: Analysis complete for {username}.")
    return jsonify({"status": "complete", "message": "Analysis complete."})

@app.route('/results')
def results():
    """
    Renders the results page with data from the saved_profiles.json.
    """
    username = session.pop('username_to_analyze', None) # Get and clear username from session
    error_message = session.pop('error_message', None) # Get and clear any error message

    if not username and not error_message:
        # If no username or error, redirect to index
        return redirect(url_for('index'))

    saved_profiles = load_saved_profiles()
    full_analysis_data = saved_profiles.get(username)

    if not full_analysis_data:
        # This case should ideally not happen if perform_analysis succeeded, but for robustness
        return render_template('results.html',
                               username=username,
                               profile=None,
                               latest_posts=[],
                               ai_analysis_text="Error: Analysis data not found for this profile.",
                               ai_overall_score=0,
                               error_message="Analysis data could not be loaded. Please try again.")

    profile_data = full_analysis_data.get('profile_data', {})
    ai_analysis = full_analysis_data.get('ai_analysis', {})

    return render_template('results.html',
                           username=username,
                           profile=profile_data.get('profile'),
                           latest_posts=profile_data.get('latestPosts', []),
                           ai_analysis_text=ai_analysis.get('text', "AI analysis not available."),
                           ai_overall_score=ai_analysis.get('score', 0),
                           error_message=error_message)

if __name__ == '__main__':
    app.run(debug=True) # debug=True allows for automatic reloading on code changes
