# main.py
import os
import tempfile
from PIL import Image

import firebase_admin
from firebase_functions import storage_fn
from firebase_admin import storage

# Initialize the Firebase Admin SDK.
# This is required to interact with Firebase services.
firebase_admin.initialize_app()


@storage_fn.on_object_finalized()
def remove_exif(event: storage_fn.CloudEvent[storage_fn.StorageObjectData]):
    """
    Triggers when a new file is uploaded to Firebase Storage,
    removes its EXIF data if it's an image, and saves it back.
    """
    
    bucket_name = event.data.bucket
    file_path = event.data.name
    content_type = event.data.content_type

    # 1. Exit if the file is not an image.
    if not content_type or not content_type.startswith("image/"):
        print(f"File '{file_path}' is not an image. Skipping.")
        return

    # 2. Safeguard: Exit if the image has already been processed to prevent loops.
    if event.data.metadata and event.data.metadata.get("processed") == "true":
        print(f"Image '{file_path}' has already been processed. Skipping.")
        return

    print(f"Processing image: {file_path}")

    bucket = storage.bucket(bucket_name)
    source_blob = bucket.blob(file_path)
    
    # 3. Use a temporary file to download and process the image.
    # This ensures the file is cleaned up automatically from the function's environment.
    _, temp_local_path = tempfile.mkstemp()
    
    try:
        # Download the image to the temporary file.
        source_blob.download_to_filename(temp_local_path)
        print(f"Image downloaded to temporary file: {temp_local_path}")
        
        # 4. Use Pillow to open the image and remove EXIF data.
        with Image.open(temp_local_path) as img:
            # Get the image data without the EXIF info.
            # A new image is created from the raw pixel data.
            img_data = list(img.getdata())
            img_no_exif = Image.new(img.mode, img.size)
            img_no_exif.putdata(img_data)

            # Save the new image (without EXIF) back to the temporary file path.
            img_no_exif.save(temp_local_path, format=img.format)
            print("EXIF data removed successfully.")

        # 5. Re-upload the sanitized image, overwriting the original.
        # This section contains the fix for the local emulator.
        destination_blob = bucket.blob(file_path)
        
        # Define new metadata, adding the 'processed' flag to prevent re-triggering.
        new_metadata = {"contentType": content_type, "processed": "true"}
        destination_blob.metadata = new_metadata
        
        # Upload the cleaned file from the temporary path with the new metadata.
        # This avoids the unsupported .patch() method.
        destination_blob.upload_from_filename(
            temp_local_path,
            content_type=content_type
        )
        print(f"Sanitized image uploaded to '{file_path}'.")

    finally:
        # 6. Clean up the temporary file from the Cloud Function's instance.
        os.remove(temp_local_path)
        print(f"Cleaned up temporary file and finished processing.")