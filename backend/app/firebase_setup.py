"""
Firebase Configuration

Initializes the Firebase Admin SDK.
"""

import firebase_admin
from firebase_admin import credentials, firestore
from pathlib import Path
import os

# Path to service account key
SERVICE_ACCOUNT_KEY = Path(__file__).parent.parent / "serviceAccountKey.json"

if not SERVICE_ACCOUNT_KEY.exists():
    raise FileNotFoundError(f"Service account key not found at {SERVICE_ACCOUNT_KEY}")

# Initialize Firebase Admin
if not firebase_admin._apps:
    cred = credentials.Certificate(str(SERVICE_ACCOUNT_KEY))
    firebase_admin.initialize_app(cred)

# Get Firestore client
db = firestore.client()
