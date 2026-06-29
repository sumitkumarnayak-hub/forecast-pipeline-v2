"""Auth router — login / logout / me."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.deps import create_access_token, get_current_user, get_db
from planning_suite.db.engine import Database
from planning_suite.services.login_sync import load_user_preferences

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = True


class LoginResponse(BaseModel):
    token: str
    user: dict


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Database = Depends(get_db)):
    user = db.authenticate_user(body.username.strip(), body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Mirror what _complete_login does in Streamlit auth
    db.update_last_login(user["id"])
    try:
        load_user_preferences(user["id"], db)
    except Exception:
        pass

    token = create_access_token(user, remember_me=body.remember_me)
    return LoginResponse(token=token, user=user)


@router.get("/me")
def me(current_user: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    """Return full user record from DB using token sub."""
    user_id = int(current_user["sub"])
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    prefs = db.get_user_preferences(user_id) or {}
    return {**user, "preferences": prefs}


@router.post("/logout")
def logout(current_user: dict = Depends(get_current_user)):
    # JWT is stateless — client simply discards the token
    return {"detail": "Logged out successfully"}
