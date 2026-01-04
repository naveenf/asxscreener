"""
Portfolio Routes

CRUD operations for user portfolio items using Firestore.
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from typing import List
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime

from ..firebase_setup import db
from ..models.portfolio_schema import PortfolioItemCreate, PortfolioItemResponse
from ..config import settings

router = APIRouter(prefix="/api/portfolio")

async def get_current_user_email(authorization: str = Header(...)) -> str:
    """
    Dependency to get user email from Google ID token.
    Expects 'Authorization: Bearer <token>'
    """
    try:
        token = authorization.replace("Bearer ", "")
        id_info = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID
        )
        email = id_info.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
        return email
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@router.get("", response_model=List[PortfolioItemResponse])
async def list_portfolio(email: str = Depends(get_current_user_email)):
    """Get all items in user's portfolio from Firestore."""
    try:
        portfolio_ref = db.collection('users').document(email).collection('portfolio')
        docs = portfolio_ref.stream()
        
        items = []
        for doc in docs:
            data = doc.to_dict()
            # Convert timestamp/string dates to date objects if needed, 
            # but schema expects date. 
            # Firestore stores as Timestamp or String. Let's assume we store as string YYYY-MM-DD
            # or handle the conversion.
            
            # Helper to parse date
            buy_date = data.get('buy_date')
            if isinstance(buy_date, str):
                buy_date = datetime.strptime(buy_date, "%Y-%m-%d").date()
            
            items.append(PortfolioItemResponse(
                id=doc.id,
                ticker=data.get('ticker'),
                buy_date=buy_date,
                buy_price=data.get('buy_price'),
                quantity=data.get('quantity'),
                notes=data.get('notes')
            ))
        return items
    except Exception as e:
        print(f"Portfolio List Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch portfolio")

@router.post("", response_model=PortfolioItemResponse)
async def add_to_portfolio(
    item: PortfolioItemCreate,
    email: str = Depends(get_current_user_email)
):
    """Add a new stock to portfolio in Firestore."""
    try:
        portfolio_ref = db.collection('users').document(email).collection('portfolio')
        
        # Prepare data (store date as string for simplicity in Firestore)
        doc_data = {
            'ticker': item.ticker,
            'buy_date': item.buy_date.isoformat(),
            'buy_price': item.buy_price,
            'quantity': item.quantity,
            'notes': item.notes,
            'created_at': datetime.utcnow()
        }
        
        # Add document (auto-generated ID)
        update_time, doc_ref = portfolio_ref.add(doc_data)
        
        return PortfolioItemResponse(
            id=doc_ref.id,
            ticker=item.ticker,
            buy_date=item.buy_date,
            buy_price=item.buy_price,
            quantity=item.quantity,
            notes=item.notes
        )
    except Exception as e:
        print(f"Portfolio Add Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to add item")

@router.delete("/{item_id}")
async def remove_from_portfolio(
    item_id: str,
    email: str = Depends(get_current_user_email)
):
    """Remove a stock from portfolio in Firestore."""
    try:
        doc_ref = db.collection('users').document(email).collection('portfolio').document(item_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Item not found")
            
        doc_ref.delete()
        return {"message": "Item removed"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Portfolio Delete Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete item")