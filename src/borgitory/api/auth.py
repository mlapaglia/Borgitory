from fastapi import APIRouter, Request, HTTPException, Depends, Response, Form
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
import secrets
from datetime import timedelta
from borgitory.utils.datetime_utils import now_utc
from typing import Dict, Optional

from borgitory.models.database import User, UserSession
from borgitory.dependencies import get_db
from borgitory.dependencies import TemplatesDep
from starlette.templating import _TemplateResponse

router = APIRouter()


@router.get("/check-users")
async def check_users_exist(
    request: Request, templates: TemplatesDep, db: AsyncSession = Depends(get_db)
) -> _TemplateResponse:
    result = await db.execute(select(func.count(User.id)))
    user_count = result.scalar() or 0
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
async def register_user(
    request: Request,
    templates: TemplatesDep,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> _TemplateResponse:
    try:
        result = await db.execute(select(func.count(User.id)))
        user_count = result.scalar() or 0
        if user_count > 0:
            return templates.TemplateResponse(
                request,
                "partials/shared/notification.html",
                {"type": "error", "message": "Registration is closed"},
                status_code=403,
            )

        result = await db.execute(select(User).where(User.username == username))
        existing_user = result.scalar_one_or_none()
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
        await db.commit()
        await db.refresh(user)

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
async def login_user(
    request: Request,
    templates: TemplatesDep,
    username: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    next: str = Form("/repositories"),
    db: AsyncSession = Depends(get_db),
) -> _TemplateResponse:
    try:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
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

        await db.execute(
            delete(UserSession).where(
                UserSession.user_id == user.id, UserSession.expires_at < now_utc()
            )
        )

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
        await db.commit()

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
async def logout(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    auth_token = request.cookies.get("auth_token")
    if auth_token:
        await db.execute(
            delete(UserSession).where(UserSession.session_token == auth_token)
        )
        await db.commit()

    response.delete_cookie("auth_token")
    return {"status": "logged out"}


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    auth_token = request.cookies.get("auth_token")
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(
        select(UserSession).where(
            UserSession.session_token == auth_token,
            UserSession.expires_at > now_utc(),
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=401, detail="Session expired")

    if not session.remember_me:
        session.expires_at = now_utc() + timedelta(minutes=30)
        session.last_activity = now_utc()
        await db.commit()

    user_result = await db.execute(select(User).where(User.id == session.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        await db.delete(session)
        await db.commit()
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def get_current_user_optional(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None
