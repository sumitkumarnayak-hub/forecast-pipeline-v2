"""Auth router — login / logout / me."""
from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel

from app.auth_cookies import clear_auth_cookie, set_auth_cookie
from app.deps import create_access_token, get_current_user, get_db
from planning_suite.db.engine import Database

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

    token = create_access_token(user, remember_me=body.remember_me)
    set_auth_cookie(response, token, remember_me=body.remember_me)

    try:
        db.update_last_login(user["id"])
    except Exception:
        pass

    return LoginResponse(user=user)


@router.get("/me")
def me(current_user: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    """Return full user record from DB using token sub."""
    from planning_suite.services.api_cache import CacheNS, cached

    user_id = int(current_user["sub"])

    def _build():
        user = db.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        prefs = db.get_user_preferences(user_id) or {}
        return {**user, "preferences": prefs}

    return cached(CacheNS.USER_PROFILE, str(user_id), _build, ttl=45.0)


@router.post("/logout")
def logout(response: Response):
    clear_auth_cookie(response)
    return {"detail": "Logged out successfully"}
