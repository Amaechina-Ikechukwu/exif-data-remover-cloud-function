## exif-remover

Small Firebase Cloud Function (Python) that automatically strips EXIF metadata from images uploaded to Cloud Storage.

Key points
- Trigger: Storage object finalized (new upload).
- Runtime: Python 3.13 (configured in `firebase.json`).
- Processing: Uses Pillow to open images and re-save them without EXIF, then re-uploads the sanitized file with a `processed=true` metadata flag to avoid re-processing loops.

Files of interest
- `functions/main.py` — Cloud Function implementation.
- `functions/requirements.txt` — pinned Python dependency manifest (currently lists `firebase_functions`).
- `firebase.json` — Firebase project configuration (functions runtime, emulator ports).
- `storage.rules` — Storage security rules (currently denies all read/write).

Quickstart (development)

1) Ensure you have the Firebase CLI installed and logged in.

2) Use Python 3.13 (the functions runtime is set to `python313`). Create and activate a venv (Windows cmd example):

```cmd
python -m venv .venv
.venv\Scripts\activate
```

3) Install dependencies. The repository's `functions/requirements.txt` currently lists `firebase_functions`. The function also needs `firebase-admin` and `Pillow` (PIL). To install all required packages:

```cmd
pip install -r functions\requirements.txt
pip install firebase-admin Pillow
```

You can pin those packages into `functions/requirements.txt` if you plan to deploy.

Running locally with the emulator

1) Start the Firebase emulators from the repo root (this uses the ports declared in `firebase.json`):

```cmd
firebase emulators:start
```

2) Upload a test image to the Storage emulator (you can use the Firebase Console UI at the emulator URL, or use `gsutil`/other tools pointed at the emulator).

Deploying

1) When ready, deploy functions and storage rules:

```cmd
firebase deploy --only functions,storage
```

Notes & Gotchas
- The function checks content type (must start with `image/`) and skips non-images.
- To prevent re-trigger loops the function sets a `processed` metadata flag. If you modify metadata behavior, keep this in mind.
- Current `storage.rules` denies all reads/writes; update it for your project before production use.
- `functions/requirements.txt` should include `firebase-admin` and `Pillow` before deploying. Example minimal contents:

```
firebase_functions~=0.1.0
firebase-admin
Pillow
```

Security
- Storage rules live in `storage.rules`. The repository currently sets a deny-all rule. Review and replace with rules appropriate for your app and auth model before enabling public or production access.

Contact / next steps
- If you want, I can:
  - Add `firebase-admin` and `Pillow` to `functions/requirements.txt` and pin versions.
  - Add a tiny integration test script to upload an image to the emulator and verify EXIF removal.

Requirements coverage
- "scan codebase" — Done (inspected `functions/main.py`, `functions/requirements.txt`, `firebase.json`, `storage.rules`).
- "add readme.md" — Done (this file).
