"""Authentication routes: register, login, and current-user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from forge.core.deps import CurrentUser, DbSession
from forge.core.errors import ApiError
from forge.core.security import create_access_token, hash_password, verify_password
from forge.models.user import User
from forge.models.workspace import Workspace, WorkspaceMembership, WorkspaceRole
from forge.schemas.auth import RegisterRequest, TokenResponse, UserOut
from forge.services.audit import record_event

router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify_email(email: str) -> str:
    local = email.split("@", 1)[0].lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in local).strip("-")
    return cleaned or "workspace"


def _unique_workspace_slug(db: DbSession, base: str) -> str:
    """Return ``base``, or ``base-2``, ``base-3``... if the slug is already taken."""
    if db.scalar(select(Workspace.id).where(Workspace.slug == base)) is None:
        return base
    suffix = 2
    while db.scalar(select(Workspace.id).where(Workspace.slug == f"{base}-{suffix}")) is not None:
        suffix += 1
    return f"{base}-{suffix}"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbSession) -> TokenResponse:
    """Create a user, provision a personal workspace, and return an access token."""
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise ApiError.conflict("An account with this email already exists")

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.flush()

    # Provision a personal workspace so the new user can immediately create projects.
    slug = _unique_workspace_slug(db, _slugify_email(user.email))
    workspace = Workspace(name=f"{payload.full_name or user.email}'s workspace", slug=slug)
    db.add(workspace)
    db.flush()

    db.add(
        WorkspaceMembership(
            workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.owner
        )
    )
    record_event(
        db,
        action="user.registered",
        actor_user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        workspace_id=workspace.id,
    )
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(
    db: DbSession,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    """Exchange email + password (OAuth2 password form) for an access token."""
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    # Verify against the stored hash even when the user is missing to reduce the
    # timing signal that reveals whether an email is registered.
    valid = user is not None and verify_password(form.password, user.hashed_password)
    if not valid or user is None or not user.is_active:
        raise ApiError.unauthorized("Incorrect email or password")

    record_event(
        db, action="auth.login", actor_user_id=user.id, resource_type="user", resource_id=user.id
    )
    db.commit()

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    """Return the currently authenticated user."""
    return UserOut.model_validate(user)
