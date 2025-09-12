from fastapi import APIRouter, Request, HTTPException, Depends, Response, Form
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import secrets
from datetime import datetime, timedelta, UTC
from typing import Optional

from app.models.database import User, UserSession, get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/check-users")
def check_users_exist(request: Request, db: Session = Depends(get_db)):
    user_count = db.query(User).count()
    has_users = user_count > 0

    # Return the appropriate form template based on user existence
    if has_users:
        # Show login form for existing users
        return templates.TemplateResponse(
            request, "partials/auth/login_form_active.html", {}
        )
    else:
        # Show welcome message and register form for first user
        return templates.TemplateResponse(
            request, "partials/auth/register_form_active.html", {}
        )


@router.post("/register")
def register_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        # Check if any users exist
        user_count = db.query(User).count()
        if user_count > 0:
            return templates.TemplateResponse(
                request,
                "partials/shared/notification.html",
                {"type": "error", "message": "Registration is closed"},
                status_code=403,
            )

        # Check if username already exists
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            return templates.TemplateResponse(
                request,
                "partials/shared/notification.html",
                {"type": "error", "message": "Username already exists"},
                status_code=400,
            )

        # Validate inputs
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

        # Create new user
        user = User(username=username.strip())
        user.set_password(password)

        db.add(user)
        db.commit()
        db.refresh(user)

        # Return success response
        return templates.TemplateResponse(
            request,
            "partials/shared/notification.html",
            {
                "type": "success",
                "message": "Registration successful! You can now log in.",
            },
        )

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
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    db: Session = Depends(get_db),
):
    try:
        # Find user
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.verify_password(password):
            return templates.TemplateResponse(
                request,
                "partials/shared/notification.html",
                {"type": "error", "message": "Invalid username or password"},
                status_code=401,
            )

        # Create session token
        auth_token = secrets.token_urlsafe(32)

        if remember_me:
            expires_at = datetime.now(UTC) + timedelta(days=365)
            max_age = 365 * 24 * 60 * 60
        else:
            expires_at = datetime.now(UTC) + timedelta(minutes=30)
            max_age = 30 * 60

        # Clean up expired sessions
        db.query(UserSession).filter(
            UserSession.user_id == user.id, UserSession.expires_at < datetime.now(UTC)
        ).delete()

        # Create new session
        user_agent = request.headers.get("user-agent") if request else None
        client_ip = (
            request.client.host if request and hasattr(request, "client") else None
        )
        current_time = datetime.now(UTC)

        db_session = UserSession(
            user_id=user.id,
            session_token=auth_token,
            expires_at=expires_at,
            remember_me=remember_me,
            user_agent=user_agent,
            ip_address=client_ip,
            created_at=current_time,
            last_activity=current_time,
        )
        db.add(db_session)

        # Update user's last login
        user.last_login = current_time
        db.commit()

        # Create success template response with redirect and set cookie
        success_response = templates.TemplateResponse(
            request,
            "partials/shared/notification.html",
            {
                "type": "success",
                "message": "Login successful! Redirecting...",
                "redirect_url": "/",
                "redirect_delay": 1000,
            },
        )
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
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth_token = request.cookies.get("auth_token")
    if auth_token:
        # Delete session from database
        db.query(UserSession).filter(UserSession.session_token == auth_token).delete()
        db.commit()

    # Clear cookie
    response.delete_cookie("auth_token")
    return {"status": "logged out"}


def get_current_user(request: Request, db: Session = Depends(get_db)):
    auth_token = request.cookies.get("auth_token")
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = (
        db.query(UserSession)
        .filter(
            UserSession.session_token == auth_token,
            UserSession.expires_at > datetime.now(UTC),
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=401, detail="Session expired")

    # Update session activity for non-remember sessions
    if not session.remember_me:
        session.expires_at = datetime.now(UTC) + timedelta(minutes=30)
        session.last_activity = datetime.now(UTC)
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
