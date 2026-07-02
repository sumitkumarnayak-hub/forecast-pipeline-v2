"""Auth router — login / logout / me."""
from fastapi import APIRouter, HTTPException, Depends, Response, Request
from pydantic import BaseModel

from app.auth_cookies import clear_auth_cookie, set_auth_cookie
from app.deps import create_access_token, get_current_user, get_db
from app.rate_limit import check_login_allowed, clear_login_attempts, record_login_failure
from planning_suite.db.engine import Database

router = APIRouter()


def _client_key(request: Request, username: str) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"{ip}:{username.strip().lower()}"


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = True


class LoginResponse(BaseModel):
    user: dict


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Database = Depends(get_db)):
    key = _client_key(request, body.username)
    if not check_login_allowed(key):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait a few minutes and try again.",
        )

    user = db.authenticate_user(body.username.strip(), body.password)
    if not user:
        record_login_failure(key)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    clear_login_attempts(key)
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
