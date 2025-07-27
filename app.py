from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from apify_client import ApifyClient
import time
import os
import json
import requests # Used for making HTTP requests to external APIs
import re # Import re for regex operations
from datetime import datetime # Import datetime for timestamping logs
import base64 # Import base64 for image encoding
from concurrent.futures import ThreadPoolExecutor # Import for concurrent processing

app = Flask(__name__)
# Set a secret key for session management. CHANGE THIS IN PRODUCTION!
app.secret_key = os.urandom(24)

# Your API Keys (LOAD FROM ENVIRONMENT VARIABLES IN PRODUCTION!)
# It's highly recommended to load these from environment variables (e.g., os.environ.get("APIFY_API_TOKEN"))
# instead of hardcoding them, especially for production.
APIFY_API_TOKEN = "" # Replace with your Apify API token
# Note: The provided key format 'sk-proj-...' is typically for Google Gemini.
# If you intend to use OpenAI, please ensure you have a valid OpenAI API key.
# The code targets the OpenAI endpoint, assuming you will use an OpenAI key.
AI_API_KEY = "" # UPDATED API KEY

# Number of recent posts to scrape for the profile
NUM_POSTS_TO_SCRAPE = 5
# Number of comments to fetch for each post using the dedicated comment scraper
NUM_COMMENTS_TO_FETCH_PER_POST = 5

# Path to the saved profiles JSON file
SAVED_PROFILES_FILE = 'saved_profiles.json'
# Path to the raw Apify logs file
APIFY_RAW_LOG_FILE = 'apify_raw_logs.jsonl' # .jsonl for JSON Lines format

# GLOBAL DICTIONARY to store analysis progress for each user
# This allows progress updates to be visible to concurrent requests
global_analysis_progress = {}

# Initialize ThreadPoolExecutor for concurrent comment scraping
# Max workers can be adjusted based on desired concurrency and system resources
executor = ThreadPoolExecutor(max_workers=5) # Allows up to 5 comment scraping tasks concurrently

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

def update_progress(username, status, percentage):
    """Updates the global analysis progress for a given username."""
    global_analysis_progress[username] = {'status': status, 'percentage': percentage}
    print(f"Server: Progress for {username}: {status} ({percentage}%)")

def fetch_image_as_base64(image_url):
    """
    Fetches an image from a URL and returns its Base64 encoded string.
    Returns an empty string if fetching fails.
    """
    if not image_url:
        return ''
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status() # Raise an exception for HTTP errors
        # Determine content type (e.g., image/jpeg, image/png)
        content_type = response.headers.get('Content-Type', 'image/jpeg') # Default to jpeg if not found
        base64_encoded_image = base64.b64encode(response.content).decode('utf-8')
        return f"data:{content_type};base64,{base64_encoded_image}"
    except requests.exceptions.RequestException as e:
        print(f"Server: Error fetching image from {image_url}: {e}")
        return ''
    except Exception as e:
        print(f"Server: Unexpected error during image Base64 encoding for {image_url}: {e}")
        return ''

def _scrape_comments_for_single_post(client, post_shortcode, num_comments_to_fetch):
    """
    Helper function to scrape comments for a single post.
    Designed to be run concurrently.
    """
    if not post_shortcode:
        return [] # Return empty list if no shortcode

    post_url = f"https://www.instagram.com/p/{post_shortcode}/"
    print(f"Server: ▶ Gathering {num_comments_to_fetch} interactions for Post: {post_url} (Concurrent)...")
    try:
        comments_input = {
            "directUrls": [post_url],
            "resultsLimit": num_comments_to_fetch
        }
        run_comments = client.actor("apify/instagram-comment-scraper").call(run_input=comments_input)
        comments_dataset_items = list(client.dataset(run_comments["defaultDatasetId"]).iterate_items())
        return comments_dataset_items
    except Exception as e:
        print(f"Server: Error scraping comments for {post_url}: {e}")
        return []

def scrape_instagram_profile_and_comments(username):
    """
    Scrapes an Instagram profile and its recent posts with comments using Apify.
    Fetches comments concurrently.
    Returns a dictionary of scraped data or None on failure.
    """
    client = ApifyClient(APIFY_API_TOKEN)
    scraped_data = {
        "profile": {},
        "latestPosts": []
    }

    print(f"Server: ▶ Scraping profile: {username} with {NUM_POSTS_TO_SCRAPE} recent posts...")
    update_progress(username, 'Scraping profile data...', 20)
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
        print(f"Server: Raw profile data from Apify for {username}: {json.dumps(profile_data, indent=2)}")
        log_apify_raw_data(username, profile_data)

        profile_pic_url = profile_data.get('profilePicUrl')
        profile_pic_base64 = fetch_image_as_base64(profile_pic_url)

        scraped_data["profile"] = {
            "username": profile_data.get('username'),
            "fullName": profile_data.get('fullName'),
            "followersCount": int(profile_data.get('followersCount', 0) or 0),
            "followsCount": int(profile_data.get('followsCount', 0) or 0),
            "bio": profile_data.get('biography'),
            "profilePicUrl": profile_pic_url,
            "profilePicBase64": profile_pic_base64,
            "profileUrl": f"https://www.instagram.com/{profile_data.get('username')}/",
        }

        posts = profile_data.get("latestPosts", [])
        scraped_data["latestPosts"] = []

        update_progress(username, 'Scraping posts and comments (concurrently)...', 50)

        # 2. Scrape Comments for Each Post (concurrently)
        if posts:
            # Prepare tasks for concurrent execution
            comment_futures = {
                executor.submit(_scrape_comments_for_single_post, client, post.get('shortCode'), NUM_COMMENTS_TO_FETCH_PER_POST): post
                for post in posts[:NUM_POSTS_TO_SCRAPE]
            }

            for future in comment_futures:
                original_post = comment_futures[future]
                try:
                    comments = future.result() # Get results from the completed thread
                    post_copy = original_post.copy()
                    post_copy["comments"] = comments
                    post_copy["hashtags"] = [tag.strip("#") for tag in post_copy.get('caption', '').split() if tag.startswith('#')]
                    post_copy["likesCount"] = int(post_copy.get('likesCount', 0) or 0)
                    post_copy["commentsCount"] = int(post_copy.get('commentsCount', 0) or 0)
                    post_copy["mediaType"] = original_post.get('__typename', '').replace('Graph', '') # Use original_post for mediaType
                    scraped_data["latestPosts"].append(post_copy)
                except Exception as e:
                    print(f"Server: Error processing concurrent comment fetch for post {original_post.get('shortCode')}: {e}")
                    # If an error occurs for a specific post, still add it without comments
                    post_copy = original_post.copy()
                    post_copy["comments"] = []
                    post_copy["hashtags"] = [tag.strip("#") for tag in post_copy.get('caption', '').split() if tag.startswith('#')]
                    post_copy["likesCount"] = int(post_copy.get('likesCount', 0) or 0)
                    post_copy["commentsCount"] = int(post_copy.get('commentsCount', 0) or 0)
                    post_copy["mediaType"] = original_post.get('__typename', '').replace('Graph', '')
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
    # Update progress for AI analysis
    update_progress(data['profile']['username'], 'Analyzing with AI...', 80)

    # Determine account scale for tailored advice and scoring
    followers = data['profile']['followersCount']
    account_scale_description = ""
    score_guidance = ""

    if followers < 10000:
        account_scale_description = "a Nano/Micro-Influencer (under 10k followers). Engagement rates are typically very high, and direct, personal interaction is key."
        score_guidance = "For this scale, an engagement rate (likes + comments / followers) above 3% is excellent (9-10/10), 1.5-3% is good (7-8/10), and below 1.5% indicates significant room for improvement."
    elif followers < 100000:
        account_scale_description = "a Small/Mid-Tier Influencer (10k-100k followers). Engagement rates are still strong, and community building through active interaction is important."
        score_guidance = "For this scale, an engagement rate above 2% is excellent (9-10/10), 1-2% is good (7-8/10), and below 1% indicates significant room for improvement."
    elif followers < 500000:
        account_scale_description = "a Mid-Tier/Macro-Influencer (100k-500k followers). Maintaining high engagement is challenging, and strategic content and community management are crucial."
        score_guidance = "For this scale, an engagement rate above 1.5% is excellent (9-10/10), 0.7-1.5% is good (7-8/10), and below 0.7% indicates significant room for improvement."
    elif followers < 5000000:
        account_scale_description = "a Macro-Influencer (500k-5M followers). Engagement percentages naturally decrease, but absolute engagement numbers are high. Focus shifts to broad reach and brand partnerships."
        score_guidance = "For this scale, an engagement rate above 0.8% is excellent (9-10/10), 0.3-0.8% is good (7-8/10), and below 0.3% indicates significant room for improvement."
    else: # > 5M followers
        account_scale_description = "a Mega-Influencer or Global Brand (over 5M followers). Engagement percentages are typically very low due to sheer volume, but even small percentages represent massive absolute engagement. Focus is on brand messaging, large-scale campaigns, and strategic community management, not individual comment replies."
        score_guidance = "For this scale, an engagement rate above 0.2% is excellent (9-10/10), 0.1-0.2% is good (7-8/10), and below 0.1% indicates significant room for improvement, but always consider the absolute number of interactions."


    prompt = f"""You are an expert Instagram growth strategist. Your task is to analyze the provided Instagram profile data and generate a highly actionable, personalized roadmap for the influencer to significantly improve their presence and engagement.

    **Crucial Directives for Custom Roadmap Generation:**
    1.  **Tone:** Be honest and analytical. While acknowledging strengths, clearly articulate areas for improvement and provide constructive criticism. Avoid overly "glazing" or generic praise.
    2.  **Tailor Advice by Scale:** This profile belongs to {account_scale_description}. All advice MUST be appropriate for this scale.
    3.  **Engagement Rate Nuance:** Remember that engagement rates naturally decrease with higher follower counts. Evaluate the profile's engagement based on the provided data and the typical rates for its follower tier, not just raw numbers. {score_guidance}
    4.  **Data Limitations - Instagram Stories:** The provided data DOES NOT include insights into Instagram Stories. Therefore, when discussing Stories, frame your advice as general best practices and potential areas for exploration, rather than referencing specific story performance. Emphasize their importance for daily engagement and audience connection.
    5.  **Highly Custom & Actionable Steps with Specific References:**
        * Generate unique, specific, and creative steps tailored directly to the provided profile data.
        * **CRITICALLY: For EACH relevant recommendation, reference specific posts by their full Instagram URL (e.g., "your Reel at https://www.instagram.com/p/ABCDEF/"), their media type (Image, Video, Carousel), and their performance metrics (likes, comments, shares, saves if available) to justify recommendations.** If a full URL is not available, refer to it as "your recent [type of post] (e.g., Reel, Image, Carousel)."
        * Avoid generic advice found in basic YouTube videos. Each step should be a concrete, implementable action.
        * For each step, briefly explain *why* it's recommended and *how* the influencer can execute it.
    6.  **Focus on Engagement:** The primary goal of this roadmap is to improve engagement (likes, comments, shares, saves, story interactions).
    7.  **Overall Score:** At the very beginning of your response, provide an "Overall Score: X/10", where X is an integer from 1 to 10. This score should reflect the profile's current performance and potential for growth, *relative to its scale*.
    8.  **Comprehensive & Detailed Roadmap:**
        * Ensure each bullet point provides sufficient detail to be actionable.
        * The total response should be comprehensive but still concise, aiming for a length that adequately covers the roadmap.
        * Each main section (Strengths, Content, Engagement, Profile) should have at least 3-4 distinct, detailed bullet points, each with its own explanation of why and how.
        * **Provide a brief, personalized introductory paragraph for each main roadmap section (Content, Engagement, Profile) to set context before the bullet points.**

    **Roadmap Structure (Use these exact headings and bullet point format):**
    **Overall Score: X/10**
    [Brief, personalized summary of overall performance and potential. This should be a paragraph, not bullet points.]

    **Strengths to Leverage:**
    - [Specific strength 1, referencing data if possible, e.g., "Your consistent use of high-quality visuals, as seen in your recent Image post (https://www.instagram.com/p/ABCDEF/), creates a cohesive brand aesthetic, evidenced by its high save rate."]
    - [Specific strength 2, e.g., "Audience shows strong interest in your 'behind-the-scenes' content (e.g., your recent Video post about X), indicated by higher save rates on similar posts."]
    - [Specific strength 3]
    - [Specific strength 4]

    **Areas for Improvement & Actionable Roadmap:**
    **1. Content Strategy & Innovation:**
    [Brief introductory paragraph for Content Strategy, e.g., "To elevate your content, focus on these tailored strategies based on your audience's demonstrated interests and content performance:"]
    - [Actionable step 1, referencing specific posts/data, e.g., "Based on the high engagement (Likes: Y, Comments: Z) of your recent Video Post (https://www.instagram.com/p/ABCDEF/) about the festival, develop a series of 3 new interactive Stories next week exploring similar themes, using polls and quizzes to drive direct interaction. This leverages proven content appeal and expands reach beyond the feed."]
    - [Actionable step 2, e.g., "Your recent Carousel post about [topic] received X saves. Experiment with a new content format like Instagram Guides to curate your existing [topic] tips into easily shareable resources, promoting them via short Reels. This maximizes evergreen content value and discoverability."]
    - [Actionable step 3, e.g., "Identify 2-3 trending audio clips relevant to your niche (e.g., 'family travel vlogs') and create short-form Reels (under 15 seconds) incorporating these sounds, aiming for increased reach through discoverability. Analyze the performance of your previous Reels (e.g., your Reel about X) to understand what resonates."]
    - [Actionable step 4]

    **2. Engagement & Community Building:**
    [Brief introductory paragraph for Engagement, e.g., "To foster deeper connections and scale your community interactions, consider these targeted approaches:"]
    - [Actionable step 1, e.g., "For your follower count ({followers} followers), implement a weekly 'Community Spotlight' in Stories where you feature a follower's insightful comment or question from a recent Image post (e.g., https://www.instagram.com/p/GHIJKL/, which had many questions) and respond directly, fostering a sense of belonging and encouraging more thoughtful engagement. This personalizes interaction at scale."]
    - [Actionable step 2, e.g., "Analyze the most common questions or recurring themes in comments on your recent posts (e.g., 'What camera do you use?' from comments on your Video post about Y). Create a dedicated FAQ Reel or Highlight to proactively address them, providing value and reducing repetitive inquiries. This streamlines information delivery and builds authority."]
    - [Actionable step 3, e.g., "Host a monthly 'Live Q&A' session focusing on a highly requested topic (e.g., 'Planning Family Trips to Southend,' based on bio keywords), promoting it via countdown stickers in Stories to build anticipation and real-time interaction. This builds live community and direct connection."]
    - [Actionable step 4]

    **3. Profile & Discovery Optimization:**
    [Brief introductory paragraph for Profile Optimization, e.g., "To enhance your discoverability and convert new visitors into loyal followers, focus on these profile enhancements:"]
    - [Actionable step 1, e.g., "Refine your bio to include 2-3 highly relevant, searchable keywords from your niche (e.g., 'Southend family adventures,' 'UK travel blogger') that are not currently prominent, to improve organic searchability. This targets specific audience segments and improves SEO within Instagram."]
    - [Actionable step 2, e.g., "Optimize your 'Link in Bio' to a Linktree or similar service, showcasing your top 3 most valuable and frequently updated resources (e.g., latest blog post, event calendar, exclusive download) to drive targeted traffic. Monitor clicks to understand audience interest, similar to how you track likes on your posts."]
    - [Actionable step 3, e.g., "Collaborate with 2-3 other Southend-based micro-influencers (<50k followers) whose audience aligns with yours for cross-promotions or joint Reels, tapping into new, highly relevant local audiences. This expands your reach strategically, as seen with the success of local tags in your Image post about Z."]
    - [Actionable step 4]

    ---
    **Profile Data for Analysis:**
    Profile Username: {data['profile']['username']}
    Full Name: {data['profile']['fullName']}
    Followers: {data['profile']['followersCount']}
    Following: {data['profile']['followsCount']}
    Bio: {data['profile']['bio'] or 'Not provided'}

    Recent Posts (summarized by caption, hashtags, and full URL if available):
    """

    for index, post in enumerate(data['latestPosts']):
        caption_preview = (post['caption'][:100] + '...') if post['caption'] else 'No caption'
        hashtags = f" #{' #'.join(post['hashtags'])}" if post['hashtags'] else ''
        post_url = f"https://www.instagram.com/p/{post.get('shortCode', '')}/" if post.get('shortCode') else 'N/A'
        prompt += f"\n- Content {index + 1} (Type: {post.get('mediaType', 'N/A')}, URL: {post_url}, Likes: {post['likesCount']}, Comments: {post['commentsCount']}): \"{caption_preview}{hashtags}\""
        if post['comments'] and len(post['comments']) > 0:
            first_comment_text = post['comments'][0].get('text', 'No text available for interaction')
            first_comment_preview = (first_comment_text[:50] + '...') if first_comment_text else 'No text'
            prompt += f" First interaction: \"{first_comment_preview}\""

    analysis_text = "AI analysis could not be generated."
    overall_score = 0

    print("Server: Sending request to AI API (OpenAI endpoint)...")
    try:
        payload = {
            "model": "gpt-4", # Changed from "gpt-3.5-turbo" to "gpt-4"
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 3000 # Increased max_tokens significantly to allow for much more detailed output
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
    # Initialize progress in the global dictionary when starting a new analysis
    update_progress(username, 'Initializing analysis...', 0)
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
        # Update global progress to 100% if using cached data
        update_progress(username, 'Analysis complete (cached)!', 100)
        return jsonify({"status": "complete", "message": "Analysis complete (cached)."})

    print(f"Server: Starting analysis for username: {username}")
    time.sleep(1) # Simulate initial processing time

    # Perform real Instagram scraping
    scraped_data = scrape_instagram_profile_and_comments(username)

    if not scraped_data:
        session['error_message'] = "Failed to retrieve Instagram data. Profile might be private or non-existent."
        # Set global progress to an error state
        update_progress(username, 'Error during data retrieval!', 0)
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
    # Final global progress update
    update_progress(username, 'Analysis complete!', 100)
    return jsonify({"status": "complete", "message": "Analysis complete."})

@app.route('/analysis_progress')
def analysis_progress():
    """
    Returns the current analysis progress to the frontend.
    """
    username = session.get('username_to_analyze')
    if not username:
        # If no username in session, return a default or error state
        return jsonify({'status': 'No active analysis', 'percentage': 0})
    
    # Retrieve progress from the global dictionary
    progress = global_analysis_progress.get(username, {'status': 'Waiting for analysis to start...', 'percentage': 0})
    return jsonify(progress)


@app.route('/results')
def results():
    """
    Renders the results page with data from the saved_profiles.json.
    """
    username = session.pop('username_to_analyze', None) # Get and clear username from session
    error_message = session.pop('error_message', None) # Get and clear any error message

    # Clear analysis progress from the global dictionary once results are rendered
    if username and username in global_analysis_progress:
        del global_analysis_progress[username]

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
