import os
from google.cloud import vision
import firebase_admin
from firebase_admin import db, storage

# This check prevents re-initializing the app if it's already been done.
if not firebase_admin._apps:
    firebase_admin.initialize_app()

def analyze_image(bucket_name, file_path, metadata=None):
    """
    Uses Cloud Vision AI to tag an image and saves the tags to the Realtime Database.
    This function is designed to be called from another Cloud Function.
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
    metadata = metadata or {}
    user_id = metadata.get('uid')
    is_public = str(metadata.get('public', 'false')).lower() == 'true'

    if not user_id:
        print(f"Could not find user ID in metadata for {file_path}. Skipping analysis.")
        return

    print(f"Analyzing image: {file_path} for user: {user_id}")

    # 3. Get public URL of the image.
    image_url = blob.public_url

    # 4. Use Vision AI to detect labels.
    vision_client = vision.ImageAnnotatorClient()
    image = vision.Image()
    image.source.image_uri = f"gs://{bucket_name}/{file_path}"

    try:
        response = vision_client.label_detection(image=image)
        if response.error.message:
            raise Exception(f"Vision API Error: {response.error.message}")

        labels = [label.description for label in response.label_annotations]
        print(f"Labels detected: {', '.join(labels)}")

        # 5. Save image URL and tags to Realtime Database.
        user_db_path = f'users/{user_id}/images'
            
        image_data = {
            'imageUrl': image_url,
            'tags': labels,
            'createdAt': {".sv": "timestamp"},
            'filePath': file_path,
            'public': is_public,
            'uid': user_id
        }
        
        # Save to user's path
        user_image_ref = db.reference(user_db_path).push()
        user_image_ref.set(image_data)
        print(f"Successfully saved tags to database for user {user_id}.")

        if is_public:
            public_db_path = 'images/public'
            # Save to public path
            public_image_ref = db.reference(public_db_path).push()
            public_image_ref.set(image_data)
            print(f"Successfully saved tags to public database.")

        # 6. Update metadata with the 'tagged' flag.
        current_metadata['tagged'] = 'true'
        blob.metadata = current_metadata
        blob.patch()
        print(f"Metadata updated for '{file_path}' with 'tagged' flag.")

    except Exception as e:
        print(f"An error occurred during image analysis for '{file_path}': {e}")