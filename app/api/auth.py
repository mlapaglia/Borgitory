from fastapi import APIRouter, Request, HTTPException, Depends, Response
from sqlalchemy.orm import Session
from fido2.server import Fido2Server
from fido2.webauthn import PublicKeyCredentialRpEntity
from fido2 import cbor
import secrets
import base64
from datetime import datetime, timedelta
from typing import Optional

from app.models.database import User, Credential, UserSession, get_db

router = APIRouter()

rp = PublicKeyCredentialRpEntity(
    name="Borgitory",
    id="localhost"
)

server = Fido2Server(rp)

sessions = {}


@router.get("/check-users")
def check_users_exist(db: Session = Depends(get_db)):
    user_count = db.query(User).count()
    return {"has_users": user_count > 0, "user_count": user_count}


@router.post("/register/begin")
def begin_registration(request: dict, db: Session = Depends(get_db)):
    username = request.get("username")
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    
    user_count = db.query(User).count()
    if user_count > 0:
        existing_user = db.query(User).filter(User.username == username).first()
        if not existing_user:
            raise HTTPException(status_code=403, detail="Registration is closed")
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
    
    registration_data, state = server.register_begin(
        {
            "id": str(user.id).encode(),
            "name": username,
            "displayName": username
        }
    )
    
    registration_data_json = dict(registration_data)
    
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {
        "user_id": user.id,
        "state": state
    }
    
    return {
        "registration_data": registration_data_json,
        "session_id": session_id
    }


@router.post("/register/complete")
def complete_registration(
    request: dict,
    db: Session = Depends(get_db)
):
    session_id = request.get("session_id")
    credential = request.get("credential")
    
    if not session_id or not credential:
        raise HTTPException(status_code=400, detail="Missing session_id or credential")
    
    session_data = sessions.get(session_id)
    if not session_data:
        raise HTTPException(status_code=400, detail="Invalid session")
    
    try:
        auth_data = server.register_complete(
            session_data["state"],
            credential
        )
        
        db_credential = Credential(
            user_id=session_data["user_id"],
            credential_id=base64.b64encode(auth_data.credential_data.credential_id).decode(),
            public_key=cbor.encode(auth_data.credential_data.public_key),
            sign_count=auth_data.counter
        )
        
        db.add(db_credential)
        db.commit()
        
        del sessions[session_id]
        
        return {"status": "success"}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login/begin")
def begin_authentication(request: dict, db: Session = Depends(get_db)):
    username = request.get("username")
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    credentials = db.query(Credential).filter(Credential.user_id == user.id).all()
    if not credentials:
        raise HTTPException(status_code=400, detail="No credentials found")
    
    from fido2.webauthn import AttestedCredentialData
    
    creds = []
    for cred in credentials:
        credential_data = AttestedCredentialData.create(
            aaguid=b'\x00' * 16,
            credential_id=base64.b64decode(cred.credential_id),
            public_key=cbor.decode(cred.public_key)
        )
        creds.append(credential_data)
    
    auth_data, state = server.authenticate_begin(creds)
    
    auth_data_json = dict(auth_data)
    
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {
        "user_id": user.id,
        "state": state
    }
    
    return {
        "auth_data": auth_data_json,
        "session_id": session_id
    }


@router.post("/login/complete")
def complete_authentication(
    request_data: dict,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    session_id = request_data.get("session_id")
    credential = request_data.get("credential")
    remember_me = request_data.get("remember_me", False)
    
    if not session_id or not credential:
        raise HTTPException(status_code=400, detail="Missing session_id or credential")
    
    session_data = sessions.get(session_id)
    if not session_data:
        raise HTTPException(status_code=400, detail="Invalid session")
    
    try:
        credentials = db.query(Credential).filter(
            Credential.user_id == session_data["user_id"]
        ).all()
        
        from fido2.webauthn import AttestedCredentialData
        
        creds = []
        for cred in credentials:
            credential_data = AttestedCredentialData.create(
                aaguid=b'\x00' * 16,
                credential_id=base64.b64decode(cred.credential_id),
                public_key=cbor.decode(cred.public_key)
            )
            creds.append(credential_data)
        
        server.authenticate_complete(
            session_data["state"],
            creds,
            credential
        )
        
        auth_token = secrets.token_urlsafe(32)
        
        if remember_me:
            expires_at = datetime.utcnow() + timedelta(days=365)
            max_age = 365 * 24 * 60 * 60
        else:
            expires_at = datetime.utcnow() + timedelta(minutes=30)
            max_age = 30 * 60
        
        user_agent = request.headers.get("user-agent") if request else None
        client_ip = request.client.host if request and hasattr(request, 'client') else None
        db.query(UserSession).filter(
            UserSession.user_id == session_data["user_id"],
            UserSession.expires_at < datetime.utcnow()
        ).delete()
        
        db_session = UserSession(
            user_id=session_data["user_id"],
            session_token=auth_token,
            expires_at=expires_at,
            remember_me=remember_me,
            user_agent=user_agent,
            ip_address=client_ip,
            last_activity=datetime.utcnow()
        )
        db.add(db_session)
        
        user = db.query(User).filter(User.id == session_data["user_id"]).first()
        if user:
            user.last_login = datetime.utcnow()
        
        db.commit()
        
        response.set_cookie(
            key="auth_token",
            value=auth_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=max_age
        )
        
        del sessions[session_id]
        
        return {"status": "success", "remember_me": remember_me}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth_token = request.cookies.get("auth_token")
    if auth_token:
        if auth_token in sessions:
            del sessions[auth_token]
        
        db.query(UserSession).filter(UserSession.session_token == auth_token).delete()
        db.commit()
    
    response.delete_cookie("auth_token")
    return {"status": "logged out"}


def get_current_user(request: Request, db: Session = Depends(get_db)):
    auth_token = request.cookies.get("auth_token")
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    session = db.query(UserSession).filter(
        UserSession.session_token == auth_token,
        UserSession.expires_at > datetime.utcnow()
    ).first()
    
    if not session:
        raise HTTPException(status_code=401, detail="Session expired")
    
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


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None