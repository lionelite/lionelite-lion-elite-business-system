import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db


router = APIRouter(tags=["saas"])
WELCOME_PATH = Path(__file__).with_name("welcome.html")
APP_HOME_PATH = Path(__file__).with_name("app_home.html")
SESSION_COOKIE = "lei_session"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(30), default="trial", index=True)
    subscription_status: Mapped[str] = mapped_column(String(30), default="trialing", index=True)
    billing_customer_id: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SaaSUser(Base):
    __tablename__ = "saas_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("saas_users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("saas_users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    company_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def _password_valid(password: str, encoded: str) -> bool:
    try:
        _, rounds, salt, expected = encoded.split("$", 3)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:70]
    return clean or "workspace"


def _new_session(db: Session, user_id: int, organization_id: int) -> str:
    token = secrets.token_urlsafe(40)
    db.add(UserSession(
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        user_id=user_id,
        organization_id=organization_id,
        expires_at=datetime.utcnow() + timedelta(days=30),
    ))
    db.commit()
    return token


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        samesite="lax",
    )


def current_workspace(
    lei_session: str | None = Cookie(default=None), db: Session = Depends(get_db)
) -> tuple[SaaSUser, Organization, OrganizationMember]:
    if not lei_session:
        raise HTTPException(status_code=401, detail="Sign in required")
    token_hash = hashlib.sha256(lei_session.encode()).hexdigest()
    session = db.scalar(select(UserSession).where(
        UserSession.token_hash == token_hash,
        UserSession.expires_at > datetime.utcnow(),
    ))
    if not session:
        raise HTTPException(status_code=401, detail="Session expired")
    user = db.get(SaaSUser, session.user_id)
    organization = db.get(Organization, session.organization_id)
    member = db.scalar(select(OrganizationMember).where(
        OrganizationMember.user_id == session.user_id,
        OrganizationMember.organization_id == session.organization_id,
    ))
    if not user or not user.active or not organization or not member:
        raise HTTPException(status_code=401, detail="Workspace access unavailable")
    return user, organization, member


@router.get("/", response_class=HTMLResponse)
def welcome() -> str:
    return WELCOME_PATH.read_text(encoding="utf-8")


@router.get("/app", response_class=HTMLResponse)
def app_home(_workspace=Depends(current_workspace)) -> str:
    return APP_HOME_PATH.read_text(encoding="utf-8")


@router.post("/saas/api/signup", status_code=201)
def signup(payload: SignupRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    email = str(payload.email).lower()
    if db.scalar(select(SaaSUser).where(SaaSUser.email == email)):
        raise HTTPException(status_code=409, detail="An account already exists for this email")
    base_slug = _slug(payload.company_name)
    slug = base_slug
    suffix = 2
    while db.scalar(select(Organization).where(Organization.slug == slug)):
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    organization = Organization(name=payload.company_name.strip(), slug=slug)
    user = SaaSUser(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=_password_hash(payload.password),
    )
    db.add_all([organization, user])
    db.flush()
    db.add(OrganizationMember(organization_id=organization.id, user_id=user.id, role="owner"))
    db.commit()
    token = _new_session(db, user.id, organization.id)
    _set_session_cookie(response, token)
    return {"workspace": slug, "plan": organization.plan, "next": "/app"}


@router.post("/saas/api/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(SaaSUser).where(SaaSUser.email == str(payload.email).lower()))
    if not user or not _password_valid(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    membership = db.scalar(select(OrganizationMember).where(OrganizationMember.user_id == user.id))
    if not membership:
        raise HTTPException(status_code=403, detail="No workspace membership found")
    token = _new_session(db, user.id, membership.organization_id)
    _set_session_cookie(response, token)
    return {"next": "/app"}


@router.post("/saas/api/logout", status_code=204)
def logout(response: Response, lei_session: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> Response:
    if lei_session:
        token_hash = hashlib.sha256(lei_session.encode()).hexdigest()
        session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/saas/api/me")
def me(workspace=Depends(current_workspace)) -> dict:
    user, organization, membership = workspace
    return {
        "user": {"name": user.full_name, "email": user.email},
        "organization": {
            "name": organization.name,
            "slug": organization.slug,
            "plan": organization.plan,
            "subscription_status": organization.subscription_status,
            "onboarding_complete": organization.onboarding_complete,
        },
        "role": membership.role,
    }


@router.get("/saas/api/workspaces")
def workspaces(workspace=Depends(current_workspace), db: Session = Depends(get_db)) -> list[dict]:
    user, active, _ = workspace
    rows = db.execute(select(OrganizationMember, Organization).join(Organization, Organization.id == OrganizationMember.organization_id).where(OrganizationMember.user_id == user.id)).all()
    return [{"id": org.id, "name": org.name, "slug": org.slug, "role": member.role, "active": org.id == active.id} for member, org in rows]


@router.post("/saas/api/workspaces/{organization_id}/activate")
def activate_workspace(organization_id: int, lei_session: str | None = Cookie(default=None), workspace=Depends(current_workspace), db: Session = Depends(get_db)) -> dict:
    user, _, _ = workspace
    member = db.scalar(select(OrganizationMember).where(OrganizationMember.user_id == user.id, OrganizationMember.organization_id == organization_id))
    if not member or not lei_session:
        raise HTTPException(status_code=403, detail="You do not belong to this workspace")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hashlib.sha256(lei_session.encode()).hexdigest(), UserSession.user_id == user.id))
    if not session:
        raise HTTPException(status_code=401, detail="Session expired")
    session.organization_id = organization_id
    db.commit()
    return {"active": organization_id, "next": "/app"}
