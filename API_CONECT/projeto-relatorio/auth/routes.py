from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from . import models, schemas, services
from ..database import get_db

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

@router.post("/register", response_model=schemas.UserResponse)
def register(user_create: schemas.UserCreate, db: Session = Depends(get_db)):
    user = services.get_user_by_username(db, user_create.username)
    if user:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_password = services.get_password_hash(user_create.password)
    new_user = models.User(
        username=user_create.username,
        password_hash=hashed_password,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = services.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = services.create_access_token({"sub": user.username})
    refresh_token = services.create_refresh_token(user.id, db)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
    }

@router.post("/refresh", response_model=schemas.RefreshTokenResponse)
def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    db_token = services.verify_refresh_token(db, refresh_token)
    if not db_token:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = db_token.user
    access_token = services.create_access_token({"sub": user.username})
    return {"refresh_token": access_token}
