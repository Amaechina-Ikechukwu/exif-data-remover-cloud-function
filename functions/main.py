# main.py
import os
import tempfile
from PIL import Image

import firebase_admin
from firebase_functions import storage_fn, scheduler_fn
from firebase_admin import storage

# Import the analyze_image function from vision.py
from vision import analyze_image

# Initialize the Firebase Admin SDK.
if not firebase_admin._apps:
    firebase_admin.initialize_app()


def process_image(bucket_name, file_path, content_type, uid=None, public=None):
    """
    Downloads an image, removes its EXIF data, and saves it to a new location.
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

        # Open the image and remove EXIF data by saving it without the data.
        with Image.open(temp_local_path) as img:
            # By not passing exif data to the save method, it's stripped.
            img.save(temp_local_path, format=img.format)
        print("EXIF data removed successfully.")

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

    finally:
        # Clean up the temporary file.
        os.remove(temp_local_path)
        print(f"Cleaned up temporary file and finished processing.")




@storage_fn.on_object_finalized(bucket=os.environ.get('GCLOUD_PROJECT') + '.appspot.com', memory=512, cpu=1, region='us-central1', timeout_sec=120)
def analyze_processed_image(event: storage_fn.CloudEvent[storage_fn.StorageObjectData]):
    """
    Triggers when a processed file is uploaded to Storage, and runs the analysis.
    """
    bucket_name = event.data.bucket
    file_path = event.data.name
    metadata = event.data.metadata or {}

    # 1. Exit if the file is not in the 'processed/' directory.
    if 'processed/' not in file_path:
        print(f"File '{file_path}' is not a processed image. Skipping.")
        return

    # 2. Pass the metadata to the analysis function.
    analyze_image(bucket_name, file_path, metadata)


@storage_fn.on_object_finalized()
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

    # 1. Exit if the file is not an image.
    if not content_type or not content_type.startswith("image/"):
        print(f"File '{file_path}' is not an image. Skipping.")
        return

    # 2. Exit if the function is triggered by its own output.
    if 'processed/' in file_path:
        print(f"File '{file_path}' is already processed. Skipping.")
        return

    process_image(bucket_name, file_path, content_type, uid, public)


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

        # 1. Exit if the file is not an image.
        if not content_type or not content_type.startswith("image/"):
            continue

        # 2. Exit if the file is already processed.
        if 'processed/' in file_path:
            continue
            
        # 3. Check for a custom metadata flag to avoid re-processing
        if blob.metadata and blob.metadata.get('processed') == 'true':
            continue

        print(f"Found unprocessed image: {file_path}")
        uid = blob.metadata.get("uid") if blob.metadata else None
        public = blob.metadata.get("public") if blob.metadata else None
        process_image(bucket.name, file_path, content_type, uid, public)
                
    print("Scheduled scan finished.")


@scheduler_fn.on_schedule(schedule="every 6 hours")
def analyze_untagged_images(event: scheduler_fn.ScheduledEvent) -> None:
    """
    Scans the storage bucket for untagged images and triggers analysis.
    """
    print("Starting scheduled scan for untagged images.")
    
    bucket = storage.bucket()
    
    # List blobs in the 'processed/' directory
    blobs = bucket.list_blobs(prefix='photos/')
    
    for blob in blobs:
        # Reload the blob to get the latest metadata
        blob.reload()
        
        # Check if the blob is an image and not already tagged
        if blob.content_type and blob.content_type.startswith("image/"):
            if not blob.metadata or blob.metadata.get('tagged') != 'true':
                print(f"Found untagged image: {blob.name}")
                analyze_image(bucket.name, blob.name, blob.metadata)
                
    print("Scheduled scan for untagged images finished.")
        