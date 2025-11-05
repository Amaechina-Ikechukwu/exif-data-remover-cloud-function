# main.py
import os
import tempfile
from PIL import Image, UnidentifiedImageError  # <-- Import UnidentifiedImageError

import firebase_admin
from firebase_functions import storage_fn, scheduler_fn
from firebase_admin import storage

# Import the analyze_image function from vision.py
from vision import analyze_image, process_image_without_metadata_check

# Initialize the Firebase Admin SDK.
if not firebase_admin._apps:
    firebase_admin.initialize_app()


def process_image(bucket_name, file_path, content_type, uid=None, public=None):
    """
    Downloads an image, removes its EXIF data, and saves it to a new location.
    Returns the destination path of the processed image.
    """
    print(f"Processing image for EXIF removal: {file_path}")

    bucket = storage.bucket(bucket_name)
    source_blob = bucket.blob(file_path)

    # Use a temporary file to download and process the image.
    _, temp_local_path = tempfile.mkstemp()

    try:
        # Download the image to the temporary file.
        source_blob.download_to_filename(temp_local_path)
        print(f"Image downloaded to temporary file: {temp_local_path}")

        # --- FIX: Added try/except block for PIL errors ---
        try:
            # Open the image and remove EXIF data by saving it without the data.
            with Image.open(temp_local_path) as img:
                # Get the format before closing
                img_format = img.format
                # By not passing exif data to the save method, it's stripped.
                img.save(temp_local_path, format=img_format)
            # Image is now properly closed after exiting the context manager
            print("EXIF data removed successfully.")
        
        except UnidentifiedImageError:
            # This catches corrupted, 0-byte, or non-image files
            print(f"Error: Cannot identify image file '{file_path}'. It may be corrupted or not a valid image. Skipping EXIF removal.")
            return None  # Return None to signal failure
        # --- END FIX ---


        # Define a new destination path in the 'processed/' subfolder.
        file_name = os.path.basename(file_path)
        destination_path = f"processed/{file_name}"
        destination_blob = bucket.blob(destination_path)

        new_metadata = {}
        if uid:
            new_metadata["uid"] = uid
        if public:
            new_metadata["public"] = public

        if new_metadata:
            destination_blob.metadata = new_metadata

        # Upload the sanitized image to the new path.
        destination_blob.upload_from_filename(
            temp_local_path,
            content_type=content_type
        )
        print(f"Sanitized image uploaded to '{destination_path}'.")
        
        return destination_path

    finally:
        # Clean up the temporary file.
        # On Windows, we need to ensure the file is released before deletion
        try:
            os.remove(temp_local_path)
            print(f"Cleaned up temporary file and finished processing.")
        except PermissionError:
            print(f"Warning: Could not delete temporary file {temp_local_path}. It may be cleaned up later by the system.")




@storage_fn.on_object_finalized(bucket=os.environ.get('GCLOUD_PROJECT') + '.appspot.com', memory=512, cpu=1, region='us-central1', timeout_sec=120, secrets=["GEMINI_API_KEY"])
def analyze_processed_image(event: storage_fn.CloudEvent[storage_fn.StorageObjectData]):
    """
    Triggers when a file is uploaded to Storage.
    Only analyzes images in the 'processed/' or 'photos/' directories.
    """
    bucket_name = event.data.bucket
    file_path = event.data.name
    metadata = event.data.metadata or {}

    # 1. Exit if the file is not in a directory we want to analyze.
    if not ('processed/' in file_path or 'photos/' in file_path):
        print(f"File '{file_path}' is not in a monitored directory. Skipping.")
        return

    # 2. Get the secret key value from os.environ
    key = os.environ.get("GEMINI_API_KEY")

    # 3. Pass the key and metadata to the analysis function.
    analyze_image(bucket_name, file_path, key, metadata)


@storage_fn.on_object_finalized(secrets=["GEMINI_API_KEY"])
def remove_exif_on_upload(event: storage_fn.CloudEvent[storage_fn.StorageObjectData]):
    """
    Triggers when a new file is uploaded to Firebase Storage,
    removes its EXIF data, saves it to a new location,
    and triggers image analysis.
    """
    bucket_name = event.data.bucket
    file_path = event.data.name
    content_type = event.data.content_type
    metadata = event.data.metadata or {}
    uid = metadata.get("uid")
    public = metadata.get("public")
    file_size = event.data.size  # <-- FIX: Get the file size

    # 1. Exit if the file is not an image.
    if not content_type or not content_type.startswith("image/"):
        print(f"File '{file_path}' is not an image. Skipping.")
        return

    # --- FIX: Add 0-byte file check ---
    # 2. Exit if the file is empty (0 bytes).
    if file_size == 0:
        print(f"File '{file_path}' is 0 bytes. Skipping.")
        return
    # --- END FIX ---

    # 3. Exit if the function is triggered by its own output.
    if 'processed/' in file_path:
        print(f"File '{file_path}' is already processed. Skipping.")
        return

    # Process the image and get the destination path
    destination_path = process_image(bucket_name, file_path, content_type, uid, public)
    
    # Run vision analysis on the processed image
    # This 'if' block will now also catch the 'None' return from a failed process_image
    # if destination_path:
    #     # Get the secret key value from os.environ
    #     key = os.environ.get("GEMINI_API_KEY")
    #     # Pass the key to the analysis function
    #     process_image_without_metadata_check(bucket_name, destination_path, gemini_api_key=key)



@scheduler_fn.on_schedule(schedule="every 24 hours")
def scan_unprocessed_images(event: scheduler_fn.ScheduledEvent) -> None:
    """
    Scans the storage bucket for unprocessed images and processes them.
    """
    print("Starting scheduled scan for unprocessed images.")
    
    # Get the default bucket
    bucket = storage.bucket()
    
    blobs = bucket.list_blobs()
    
    for blob in blobs:
        file_path = blob.name
        content_type = blob.content_type
        file_size = blob.size # <-- Also good to check size here

        # 1. Exit if the file is not an image.
        if not content_type or not content_type.startswith("image/"):
            continue

        # 2. Exit if the file is empty.
        if file_size == 0:
            continue

        # 3. Exit if the file is already processed.
        if 'processed/' in file_path:
            continue
            
        # 4. Check for a custom metadata flag to avoid re-processing
        if blob.metadata and blob.metadata.get('processed') == 'true':
            continue

        print(f"Found unprocessed image: {file_path}")
        uid = blob.metadata.get("uid") if blob.metadata else None
        public = blob.metadata.get("public") if blob.metadata else None
        process_image(bucket.name, file_path, content_type, uid, public)
                
    print("Scheduled scan finished.")


@scheduler_fn.on_schedule(schedule="every 6 hours", secrets=["GEMINI_API_KEY"])
def analyze_untagged_images(event: scheduler_fn.ScheduledEvent) -> None:
    """
    Scans the storage bucket for untagged images and triggers analysis.
    """
    print("Starting scheduled scan for untagged images.")
    
    bucket = storage.bucket()
    
    # List blobs in the 'processed/' directory
    blobs = bucket.list_blobs(prefix='photos/')
    
    # Get the secret key value once from os.environ
    key = os.environ.get("GEMINI_API_KEY")
    
    for blob in blobs:
        # Reload the blob to get the latest metadata
        blob.reload()
        
        # Check if the blob is an image and not already tagged
        if blob.content_type and blob.content_type.startswith("image/"):
            if not blob.metadata or blob.metadata.get('tagged') != 'true':
                print(f"Found untagged image: {blob.name}")
                # Pass the key to the analysis function
                analyze_image(bucket.name, blob.name, key, blob.metadata)
                
    print("Scheduled scan for untagged images finished.")