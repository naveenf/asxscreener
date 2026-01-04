"""
Authentication Routes

Handles Google OAuth token verification and user session creation using Firestore.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime

from ..firebase_setup import db
from ..config import settings

router = APIRouter()

class GoogleAuthRequest(BaseModel):
    credential: str  # The ID token from Google

class AuthResponse(BaseModel):
    user_id: str
    email: str
    name: str
    token: str

@router.post("/auth/google", response_model=AuthResponse)
async def google_login(request: GoogleAuthRequest):
    """
    Verifies a Google ID token and returns user details.
    Creates/Updates the user document in Firestore.
    """
    try:
        # Verify the token with Google
        id_info = id_token.verify_oauth2_token(
            request.credential,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10
        )

        # Extract user info
        email = id_info.get("email")
        name = id_info.get("name")
        
        if not email:
            raise HTTPException(status_code=400, detail="Invalid token: Email missing")

        # Reference to the user document
        user_ref = db.collection('users').document(email)
        user_doc = user_ref.get()

        if not user_doc.exists:
            # Create new user
            user_data = {
                'email': email,
                'name': name,
                'created_at': datetime.utcnow()
            }
            user_ref.set(user_data)
        else:
            # Update last login or just ensure name is current
            user_ref.update({'name': name, 'last_login': datetime.utcnow()})
        
        return AuthResponse(
            user_id=email, # Use email as the ID
            email=email,
            name=name,
            token=request.credential
        )

    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid authentication token: {str(e)}")
    except Exception as e:
        print(f"Auth Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))