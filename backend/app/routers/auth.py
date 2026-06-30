"""Auth router — login / logout / me."""
from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel

from app.auth_cookies import clear_auth_cookie, set_auth_cookie
from app.deps import create_access_token, get_current_user, get_db
from planning_suite.db.engine import Database
from planning_suite.services.login_sync import load_user_preferences

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = True


class LoginResponse(BaseModel):
    user: dict


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, response: Response, db: Database = Depends(get_db)):
    user = db.authenticate_user(body.username.strip(), body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    db.update_last_login(user["id"])
    try:
        load_user_preferences(user["id"], db)
    except Exception:
        pass

    token = create_access_token(user, remember_me=body.remember_me)
    set_auth_cookie(response, token, remember_me=body.remember_me)
    return LoginResponse(user=user)


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
def logout(response: Response):
    clear_auth_cookie(response)
    return {"detail": "Logged out successfully"}
