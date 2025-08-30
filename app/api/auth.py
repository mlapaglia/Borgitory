from fastapi import APIRouter, Request, HTTPException, Depends, Response
from sqlalchemy.orm import Session
from fido2.server import Fido2Server
from fido2.webauthn import PublicKeyCredentialRpEntity
import secrets
import base64

from app.models.database import User, Credential, get_db

router = APIRouter()

# WebAuthn configuration
rp = PublicKeyCredentialRpEntity(
    name="Borgitory",
    id="localhost"  # Change for production
)

server = Fido2Server(rp)

# Simple in-memory session storage for MVP
sessions = {}


@router.post("/register/begin")
def begin_registration(username: str, db: Session = Depends(get_db)):
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
    
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {
        "user_id": user.id,
        "state": state
    }
    
    return {
        "registration_data": registration_data,
        "session_id": session_id
    }


@router.post("/register/complete")
def complete_registration(
    session_id: str,
    credential: dict,
    db: Session = Depends(get_db)
):
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
            public_key=auth_data.credential_data.public_key,
            sign_count=auth_data.credential_data.sign_count
        )
        
        db.add(db_credential)
        db.commit()
        
        del sessions[session_id]
        
        return {"status": "success"}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login/begin")
def begin_authentication(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    credentials = db.query(Credential).filter(Credential.user_id == user.id).all()
    if not credentials:
        raise HTTPException(status_code=400, detail="No credentials found")
    
    creds = []
    for cred in credentials:
        creds.append({
            "credential_id": base64.b64decode(cred.credential_id),
            "public_key": cred.public_key,
            "sign_count": cred.sign_count
        })
    
    auth_data, state = server.authenticate_begin(creds)
    
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {
        "user_id": user.id,
        "state": state
    }
    
    return {
        "auth_data": auth_data,
        "session_id": session_id
    }


@router.post("/login/complete")
def complete_authentication(
    session_id: str,
    credential: dict,
    response: Response,
    db: Session = Depends(get_db)
):
    session_data = sessions.get(session_id)
    if not session_data:
        raise HTTPException(status_code=400, detail="Invalid session")
    
    try:
        credentials = db.query(Credential).filter(
            Credential.user_id == session_data["user_id"]
        ).all()
        
        creds = []
        for cred in credentials:
            creds.append({
                "credential_id": base64.b64decode(cred.credential_id),
                "public_key": cred.public_key,
                "sign_count": cred.sign_count
            })
        
        server.authenticate_complete(
            session_data["state"],
            creds,
            credential
        )
        
        # Create session cookie
        auth_token = secrets.token_urlsafe(32)
        sessions[auth_token] = {"user_id": session_data["user_id"]}
        
        response.set_cookie(
            key="auth_token",
            value=auth_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax"
        )
        
        del sessions[session_id]
        
        return {"status": "success"}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/logout")
def logout(request: Request, response: Response):
    auth_token = request.cookies.get("auth_token")
    if auth_token and auth_token in sessions:
        del sessions[auth_token]
    
    response.delete_cookie("auth_token")
    return {"status": "logged out"}


def get_current_user(request: Request, db: Session = Depends(get_db)):
    auth_token = request.cookies.get("auth_token")
    if not auth_token or auth_token not in sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = sessions[auth_token]["user_id"]
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user