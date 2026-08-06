import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from taxlens.api.auth import (
    AuthenticatedUser,
    hash_password,
    require_admin,
    require_internal_token,
    verify_password,
)
from taxlens.db import get_db_session
from taxlens.legal_data.models import UserAccount

router = APIRouter(prefix="/auth", tags=["authentication"])
admin_router = APIRouter(prefix="/admin/users", tags=["administration"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    role: str


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256)
    role: str = Field(default="user", pattern="^(admin|user)$")


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=12, max_length=256)


class UserAdminResponse(UserResponse):
    is_active: bool
    created_at: datetime


@router.post("/login", response_model=UserResponse, dependencies=[Depends(require_internal_token)])
def login(request: LoginRequest, session: Session = Depends(get_db_session)) -> UserResponse:
    user = session.scalar(select(UserAccount).where(UserAccount.username == request.username))
    if (
        user is None
        or not user.is_active
        or not verify_password(request.password, user.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user.last_login_at = datetime.now(UTC)
    session.commit()
    return UserResponse(id=user.id, username=user.username, role=user.role)


@admin_router.get("", response_model=list[UserAdminResponse])
def list_users(
    _: AuthenticatedUser = Depends(require_admin), session: Session = Depends(get_db_session)
) -> list[UserAdminResponse]:
    return [
        UserAdminResponse(
            id=user.id,
            username=user.username,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
        )
        for user in session.scalars(select(UserAccount).order_by(UserAccount.username)).all()
    ]


@admin_router.post("", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    request: UserCreateRequest,
    _: AuthenticatedUser = Depends(require_admin),
    session: Session = Depends(get_db_session),
) -> UserAdminResponse:
    if session.scalar(select(UserAccount).where(UserAccount.username == request.username)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    user = UserAccount(
        username=request.username,
        password_hash=hash_password(request.password),
        role=request.role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserAdminResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@admin_router.post("/{user_id}/reset-password", response_model=UserAdminResponse)
def reset_password(
    user_id: uuid.UUID,
    request: PasswordResetRequest,
    _: AuthenticatedUser = Depends(require_admin),
    session: Session = Depends(get_db_session),
) -> UserAdminResponse:
    user = _get_user(session, user_id)
    user.password_hash = hash_password(request.password)
    session.commit()
    return _admin_response(user)


@admin_router.post("/{user_id}/disable", response_model=UserAdminResponse)
def disable_user(
    user_id: uuid.UUID,
    _: AuthenticatedUser = Depends(require_admin),
    session: Session = Depends(get_db_session),
) -> UserAdminResponse:
    user = _get_user(session, user_id)
    user.is_active = False
    session.commit()
    return _admin_response(user)


@admin_router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    current: AuthenticatedUser = Depends(require_admin),
    session: Session = Depends(get_db_session),
) -> None:
    if user_id == current.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself"
        )
    user = _get_user(session, user_id)
    session.delete(user)
    session.commit()


def _get_user(session: Session, user_id: uuid.UUID) -> UserAccount:
    user = session.get(UserAccount, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _admin_response(user: UserAccount) -> UserAdminResponse:
    return UserAdminResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )
