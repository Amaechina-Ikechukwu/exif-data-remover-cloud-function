import os
from urllib.parse import quote
import google.generativeai as genai
from google.cloud import vision
import firebase_admin
from firebase_admin import db, storage
# Do not import params here, it's not needed

# This check prevents re-initializing the app if it's already been done.
if not firebase_admin._apps:
    firebase_admin.initialize_app()

def analyze_image(bucket_name, file_path, gemini_api_key, metadata=None):
    """
    Uses Cloud Vision AI to tag an image and saves the tags to the Realtime Database.
    This function is designed to be called from another Cloud Function.
    The Gemini API key is passed as an argument.
    """
    bucket = storage.bucket(bucket_name)
    blob = bucket.blob(file_path)

    # It's crucial to reload the blob to get the very latest metadata,
    # especially if another function has just modified it.
    blob.reload()
    current_metadata = blob.metadata or {}

    # 1. Safeguard: Exit if the image has already been tagged.
    if current_metadata.get("tagged") == "true":
        print(f"Image '{file_path}' has already been tagged. Skipping analysis.")
        return

    # 2. Extract user ID and public status from metadata
    user_id = current_metadata.get('uid')
    is_public = current_metadata.get('public')

    if not user_id:
        print(f"Could not find user ID in metadata for {file_path}. Skipping analysis.")
        return

    print(f"Analyzing image: {file_path} for user: {user_id}")

    # 3. Get public URL of the image.
    image_url = blob.public_url

    # 4. Use Vision AI to detect labels.
    # Download the image content instead of using GCS URI to avoid timing issues
    vision_client = vision.ImageAnnotatorClient()
    image_content = blob.download_as_bytes()
    image = vision.Image(content=image_content)

    try:
        response = vision_client.label_detection(image=image)
        if response.error.message:
            raise Exception(f"Vision API Error: {response.error.message}")

        labels = response.label_annotations
        all_tags = [label.description for label in labels]
        
        # Use Gemini to get a smart category
        # Configure with API key passed as an argument
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')

        prompt = f"""Role: You are an expert photo organization AI. Your job is to analyze a list of raw, messy labels from Google Cloud Vision and categorize the photo into one single, user-friendly "Smart Album".

Your Smart Album categories are:

People
Pets
Places & Travel
Food & Drink
Events & Activities
Art & Design
Screenshots & Recordings
Documents & Text
Other

Respond with only the single best category name from the list. Do not add any other text.

Current File Path:
{", ".join(all_tags)}"""
        
        response = model.generate_content(prompt)
        category = response.text.strip()

        print(f"All labels detected: {', '.join(all_tags)}")
        print(f"Smart Album category: {category}")

        # 5. Save image URL and tags to Realtime Database.
        user_db_path = f'users/{user_id}/images'

        image_data = {
            'imageUrl': image_url,
            'tags': all_tags,
            'category': category,
            'createdAt': {".sv": "timestamp"},
            'filePath': file_path,
            'public': is_public,
            'uid': user_id
        }
        
        # Save to user's path (primary storage location)
        user_image_ref = db.reference(user_db_path).push()
        user_image_ref.set(image_data)
        user_image_key = user_image_ref.key
        print(f"Successfully saved tags to database for user {user_id} with key {user_image_key}.")

        if is_public:
            # Instead of duplicating data, store a reference to the user's image
            public_db_path = 'images/public'
            public_image_ref = db.reference(public_db_path).child(user_image_key)
            
            # Store a lightweight reference with essential public info
            public_reference = {
                'userImagePath': f'{user_db_path}/{user_image_key}',
                'imageUrl': image_url,
                'category': category,
                'uid': user_id,
                'createdAt': {".sv": "timestamp"}
            }
            public_image_ref.set(public_reference)
            print(f"Successfully saved public reference to database with key {user_image_key}.")

        # 6. Update metadata with analysis flags.
        current_metadata['tagged'] = 'true'
        current_metadata['processed'] = 'true'
        current_metadata['uid'] = user_id
        current_metadata['public'] = str(is_public).lower()
        blob.metadata = current_metadata
        blob.patch()
        print(f"Metadata updated for '{file_path}' with analysis flags.")

    except Exception as e:
        if "No such object" in str(e):
            print(f"Blob '{file_path}' not found during patch, likely updated by another process. Skipping.")
        else:
            print(f"An error occurred during image analysis for '{file_path}': {e}")

def process_image_without_metadata_check(bucket_name, file_path, gemini_api_key):
    """
    Uses Cloud Vision AI to tag an image for local testing without metadata checks.
    The Gemini API key is passed as an argument.
    """
    bucket = storage.bucket(bucket_name)
    blob = bucket.blob(file_path)

    print(f"Analyzing image locally: {file_path}")

    # Use Vision AI to detect labels.
    # Download the image content instead of using GCS URI to avoid timing issues
    vision_client = vision.ImageAnnotatorClient()
    image_content = blob.download_as_bytes()
    image = vision.Image(content=image_content)

    try:
        response = vision_client.label_detection(image=image)
        if response.error.message:
            raise Exception(f"Vision API Error: {response.error.message}")

        labels = response.label_annotations
        all_tags = [label.description for label in labels]
        
        # Use Gemini to get a smart category
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')

        prompt = f"""Role: You are an expert photo organization AI. Your job is to analyze a list of raw, messy labels from Google Cloud Vision and categorize the photo into one single, user-friendly "Smart Album".

Your Smart Album categories are:

People 
Pets
Places & Travel
Food & Drink
Events & Activities
Art & Design
Screenshots & Recordings
Documents & Text
Other

Respond with only the single best category name from the list. Do not add any other text.

Current File Path:
{", ".join(all_tags)}"""
        
        response = model.generate_content(prompt)
        category = response.text.strip()

        print(f"All labels detected: {', '.join(all_tags)}")
        print(f"Smart Album category: {category}")

    except Exception as e:
        print(f"An error occurred during local image analysis for '{file_path}': {e}")