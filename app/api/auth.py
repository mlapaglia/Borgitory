from fastapi import APIRouter, Request, HTTPException, Depends, Response, Form
from sqlalchemy.orm import Session
import secrets
from datetime import datetime, timedelta
from typing import Optional

from app.models.database import User, UserSession, get_db

router = APIRouter()


@router.get("/check-users")
def check_users_exist(db: Session = Depends(get_db)):
    user_count = db.query(User).count()
    return {"has_users": user_count > 0, "user_count": user_count}


@router.post("/register")
def register_user(
    username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)
):
    # Check if any users exist
    user_count = db.query(User).count()
    if user_count > 0:
        raise HTTPException(status_code=403, detail="Registration is closed")

    # Check if username already exists
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Validate inputs
    if not username or len(username.strip()) < 3:
        raise HTTPException(
            status_code=400, detail="Username must be at least 3 characters"
        )

    if not password or len(password) < 6:
        raise HTTPException(
            status_code=400, detail="Password must be at least 6 characters"
        )

    # Create new user
    user = User(username=username.strip())
    user.set_password(password)

    db.add(user)
    db.commit()
    db.refresh(user)

    return {"status": "success", "message": "User created successfully"}


@router.post("/login")
def login_user(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    db: Session = Depends(get_db),
):
    # Find user
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.verify_password(password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Create session token
    auth_token = secrets.token_urlsafe(32)

    if remember_me:
        expires_at = datetime.utcnow() + timedelta(days=365)
        max_age = 365 * 24 * 60 * 60
    else:
        expires_at = datetime.utcnow() + timedelta(minutes=30)
        max_age = 30 * 60

    # Clean up expired sessions
    db.query(UserSession).filter(
        UserSession.user_id == user.id, UserSession.expires_at < datetime.utcnow()
    ).delete()

    # Create new session
    user_agent = request.headers.get("user-agent") if request else None
    client_ip = request.client.host if request and hasattr(request, "client") else None

    db_session = UserSession(
        user_id=user.id,
        session_token=auth_token,
        expires_at=expires_at,
        remember_me=remember_me,
        user_agent=user_agent,
        ip_address=client_ip,
        last_activity=datetime.utcnow(),
    )
    db.add(db_session)

    # Update user's last login
    user.last_login = datetime.utcnow()
    db.commit()

    # Set cookie
    response.set_cookie(
        key="auth_token",
        value=auth_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=max_age,
    )

    return {"status": "success", "remember_me": remember_me}


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
            UserSession.expires_at > datetime.utcnow(),
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=401, detail="Session expired")

    # Update session activity for non-remember sessions
    if not session.remember_me:
        session.expires_at = datetime.utcnow() + timedelta(minutes=30)
        session.last_activity = datetime.utcnow()
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
