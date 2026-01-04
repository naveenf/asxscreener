# Migration to Firebase Firestore Plan

## Analysis
The user has provided the `serviceAccountKey.json`, enabling a secure **Backend-to-Firestore** migration. This preserves the existing API structure (Frontend -> Python Backend) but swaps the internal data storage from SQLite to Firestore.

**Advantages:**
*   **Security**: Credentials are kept on the server.
*   **Architecture**: Python backend remains the single API gateway.
*   **Consistency**: No need to rewrite the frontend API calls, only the backend implementation.

## Implementation Plan

### Phase 1: Setup & Dependencies
1.  **Add Dependencies**: Update `backend/requirements.txt` to include `firebase-admin`. [x]
2.  **Firebase Configuration**:
    *   Create `backend/app/firebase_setup.py` to initialize `firebase-admin` with `serviceAccountKey.json`. [x]

### Phase 2: Refactor Data Access (Backend)
3.  **Update Portfolio Schema**:
    *   Modify `backend/app/models/portfolio_schema.py` to use `str` for `id`. [x]
4.  **Refactor Authentication**:
    *   Update `backend/app/api/auth.py` to use Firestore for user lookups. [x]
5.  **Refactor Portfolio API**:
    *   Update `backend/app/api/portfolio.py` to use Firestore for CRUD operations. [x]

### Phase 3: Cleanup
6.  **Remove SQLite**:
    *   Update `backend/app/main.py` to remove SQL init. [x]
    *   Delete `backend/app/db.py`, `backend/app/models/user.py`. [x]

n. **Final Step**: Await user approval.
