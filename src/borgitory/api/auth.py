from fastapi import APIRouter, Request, HTTPException, Depends, Response, Form
from sqlalchemy.orm import Session
import secrets
from datetime import timedelta
from borgitory.utils.datetime_utils import now_utc
from typing import Dict, Optional

from borgitory.models.database import User, UserSession, get_db
from borgitory.dependencies import TemplatesDep
from starlette.templating import _TemplateResponse

router = APIRouter()


@router.get("/check-users")
def check_users_exist(
    request: Request, templates: TemplatesDep, db: Session = Depends(get_db)
) -> _TemplateResponse:
    user_count = db.query(User).count()
    has_users = user_count > 0
    next_url = request.query_params.get("next", "/repositories")

    if has_users:
        return templates.TemplateResponse(
            request, "partials/auth/login_form_active.html", {"next": next_url}
        )
    else:
        return templates.TemplateResponse(
            request, "partials/auth/register_form_active.html", {"next": next_url}
        )


@router.post("/register")
def register_user(
    request: Request,
    templates: TemplatesDep,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> _TemplateResponse:
    try:
        user_count = db.query(User).count()
        if user_count > 0:
            return templates.TemplateResponse(
                request,
                "partials/shared/notification.html",
                {"type": "error", "message": "Registration is closed"},
                status_code=403,
            )

        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            return templates.TemplateResponse(
                request,
                "partials/shared/notification.html",
                {"type": "error", "message": "Username already exists"},
                status_code=400,
            )

        if not username or len(username.strip()) < 3:
            return templates.TemplateResponse(
                request,
                "partials/shared/notification.html",
                {"type": "error", "message": "Username must be at least 3 characters"},
                status_code=400,
            )

        if not password or len(password) < 6:
            return templates.TemplateResponse(
                request,
                "partials/shared/notification.html",
                {"type": "error", "message": "Password must be at least 6 characters"},
                status_code=400,
            )

        user = User()
        user.username = username.strip()
        user.set_password(password)

        db.add(user)
        db.commit()
        db.refresh(user)

        success_response = templates.TemplateResponse(
            request,
            "partials/shared/notification.html",
            {
                "type": "success",
                "message": "Registration successful! You can now log in.",
            },
        )
        success_response.headers["HX-Trigger"] = "reload-auth-form"
        return success_response

    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/shared/notification.html",
            {"type": "error", "message": f"Registration failed: {str(e)}"},
            status_code=500,
        )


@router.post("/login")
def login_user(
    request: Request,
    templates: TemplatesDep,
    username: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    next: str = Form("/repositories"),
    db: Session = Depends(get_db),
) -> _TemplateResponse:
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.verify_password(password):
            return templates.TemplateResponse(
                request,
                "partials/shared/notification.html",
                {"type": "error", "message": "Invalid username or password"},
                status_code=401,
            )

        auth_token = secrets.token_urlsafe(32)

        if remember_me:
            expires_at = now_utc() + timedelta(days=365)
            max_age = 365 * 24 * 60 * 60
        else:
            expires_at = now_utc() + timedelta(minutes=30)
            max_age = 30 * 60

        db.query(UserSession).filter(
            UserSession.user_id == user.id, UserSession.expires_at < now_utc()
        ).delete()

        user_agent = request.headers.get("user-agent") if request else None
        client_ip = (
            request.client.host
            if request and hasattr(request, "client") and request.client
            else None
        )
        current_time = now_utc()

        db_session = UserSession()
        db_session.user_id = user.id
        db_session.session_token = auth_token
        db_session.expires_at = expires_at
        db_session.remember_me = remember_me
        db_session.user_agent = user_agent
        db_session.ip_address = client_ip
        db_session.created_at = current_time
        db_session.last_activity = current_time
        db.add(db_session)

        user.last_login = current_time
        db.commit()

        success_response = templates.TemplateResponse(
            request,
            "partials/shared/notification.html",
            {
                "type": "success",
                "message": "Login successful! Redirecting...",
            },
        )
        success_response.headers["HX-Redirect"] = next
        success_response.set_cookie(
            key="auth_token",
            value=auth_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=max_age,
        )
        return success_response

    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/shared/notification.html",
            {"type": "error", "message": f"Login failed: {str(e)}"},
            status_code=500,
        )


@router.post("/logout")
def logout(
    request: Request, response: Response, db: Session = Depends(get_db)
) -> Dict[str, str]:
    auth_token = request.cookies.get("auth_token")
    if auth_token:
        db.query(UserSession).filter(UserSession.session_token == auth_token).delete()
        db.commit()

    response.delete_cookie("auth_token")
    return {"status": "logged out"}


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth_token = request.cookies.get("auth_token")
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = (
        db.query(UserSession)
        .filter(
            UserSession.session_token == auth_token,
            UserSession.expires_at > now_utc(),
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=401, detail="Session expired")

    if not session.remember_me:
        session.expires_at = now_utc() + timedelta(minutes=30)
        session.last_activity = now_utc()
        db.commit()

    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail="User not found")

    return user


def get_current_user_optional(
    request: Request, db: Session = Depends(get_db)
) -> Optional[User]:
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None
