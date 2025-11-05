"""
Local Storage Watcher for Firebase Storage
This script monitors Firebase Storage for new file uploads and automatically
triggers Vision AI processing locally for testing purposes.
"""

import os
import time
import firebase_admin
from firebase_admin import storage
from vision import process_image_without_metadata_check
from dotenv import load_dotenv

load_dotenv()

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    firebase_admin.initialize_app()

def watch_storage_uploads(bucket_name=None, check_interval=5, watch_prefix="processed/"):
    """
    Watches Firebase Storage for new uploads and processes them with Vision AI.
    
    Args:
        bucket_name: The name of the storage bucket (defaults to project bucket)
        check_interval: How often to check for new files (in seconds)
        watch_prefix: The prefix/folder to watch for uploads (e.g., "processed/")
    """
    if not bucket_name:
        bucket_name = os.environ.get('GCLOUD_PROJECT') + '.appspot.com'
    
    print(f"Starting local storage watcher...")
    print(f"Bucket: {bucket_name}")
    print(f"Watching prefix: {watch_prefix}")
    print(f"Check interval: {check_interval} seconds")
    print(f"Press Ctrl+C to stop\n")
    
    bucket = storage.bucket(bucket_name)
    processed_files = set()
    
    # Initial scan to mark existing files as already processed
    print("Scanning for existing files...")
    blobs = bucket.list_blobs(prefix=watch_prefix)
    for blob in blobs:
        if blob.content_type and blob.content_type.startswith("image/"):
            processed_files.add(blob.name)
    print(f"Found {len(processed_files)} existing image(s). These will be skipped.\n")
    
    try:
        while True:
            # List all blobs with the specified prefix
            blobs = bucket.list_blobs(prefix=watch_prefix)
            
            for blob in blobs:
                # Check if it's an image and we haven't processed it yet
                if blob.content_type and blob.content_type.startswith("image/"):
                    if blob.name not in processed_files:
                        print(f"\n{'='*60}")
                        print(f"🔍 NEW IMAGE DETECTED: {blob.name}")
                        print(f"{'='*60}")
                        
                        # Mark as processed before running analysis
                        processed_files.add(blob.name)
                        
                        # Run Vision AI analysis
                        try:
                            process_image_without_metadata_check(bucket_name, blob.name)
                            print(f"✅ Successfully analyzed: {blob.name}")
                        except Exception as e:
                            print(f"❌ Error analyzing {blob.name}: {e}")
                        
                        print(f"{'='*60}\n")
            
            # Wait before checking again
            time.sleep(check_interval)
            
    except KeyboardInterrupt:
        print("\n\nStopping storage watcher. Goodbye!")

def process_single_file(bucket_name=None, file_path=None):
    """
    Process a single file immediately for testing.
    
    Args:
        bucket_name: The name of the storage bucket
        file_path: The path to the file in storage
    """
    if not bucket_name:
        bucket_name = os.environ.get('GCLOUD_PROJECT') + '.appspot.com'
    
    if not file_path:
        print("Error: file_path is required")
        return
    
    print(f"Processing single file: {file_path}")
    print(f"Bucket: {bucket_name}\n")
    
    try:
        process_image_without_metadata_check(bucket_name, file_path)
        print(f"\n✅ Successfully analyzed: {file_path}")
    except Exception as e:
        print(f"\n❌ Error analyzing {file_path}: {e}")

if __name__ == "__main__":
    import sys
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--single" and len(sys.argv) > 2:
            # Process a single file
            file_path = sys.argv[2]
            bucket_name = sys.argv[3] if len(sys.argv) > 3 else None
            process_single_file(bucket_name, file_path)
        else:
            print("Usage:")
            print("  Watch mode:   python local_storage_watcher.py")
            print("  Single file:  python local_storage_watcher.py --single <file_path> [bucket_name]")
    else:
        # Default: Watch mode
        # You can customize these parameters:
        watch_storage_uploads(
            bucket_name=None,  # Uses default project bucket
            check_interval=5,  # Check every 5 seconds
            watch_prefix="processed/"  # Watch the processed/ folder
        )
