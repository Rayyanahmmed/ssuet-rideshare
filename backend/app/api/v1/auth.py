"""Authentication endpoints — `/api/v1/auth` (§4)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.rate_limit import limiter
from app.models.enums import NotificationType
from app.schemas.auth import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    LogoutIn,
    RefreshIn,
    RegisterIn,
    ResetPasswordIn,
    TokenPairOut,
    VerifyEmailIn,
)
from app.schemas.common import MessageOut
from app.schemas.user import UserMeOut
from app.services import auth_service
from app.services.notification_service import create_notification

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _token_response(user, access_token: str, refresh_token: str) -> TokenPairOut:
    return TokenPairOut(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserMeOut.model_validate(user),
    )


@router.post(
    "/register",
    response_model=TokenPairOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    description=(
        "Registers a student or teacher. Accounts on a trusted university domain are "
        "verified automatically; everyone else must submit their university ID for "
        "manual admin verification. Returns a token pair so the app can sign in "
        "immediately."
    ),
)
@limiter.limit("5/minute")
def register(
    request: Request,  # required by the rate limiter
    payload: RegisterIn,
    db: DbSession,
) -> TokenPairOut:
    user, access_token, refresh_token = auth_service.register_user(
        db, payload, user_agent=request.headers.get("user-agent")
    )
    return _token_response(user, access_token, refresh_token)


@router.post(
    "/login",
    response_model=TokenPairOut,
    summary="Sign in with email and password",
    description="Returns a short-lived access token and a rotating refresh token.",
)
# 30/minute per IP: many students share one campus Wi-Fi (one public IP) and sign in together.
@limiter.limit("30/minute")
def login(request: Request, payload: LoginIn, db: DbSession) -> TokenPairOut:
    user, access_token, refresh_token = auth_service.authenticate(
        db, str(payload.email), payload.password, user_agent=request.headers.get("user-agent")
    )
    return _token_response(user, access_token, refresh_token)


@router.post(
    "/refresh",
    response_model=TokenPairOut,
    summary="Exchange a refresh token for a new pair",
    description=(
        "Rotates the refresh token. Reusing an already-rotated token is treated as "
        "theft: every session of that user is revoked."
    ),
)
@limiter.limit("30/minute")
def refresh(request: Request, payload: RefreshIn, db: DbSession) -> TokenPairOut:
    user, access_token, refresh_token = auth_service.rotate_refresh_token(
        db, payload.refresh_token, user_agent=request.headers.get("user-agent")
    )
    return _token_response(user, access_token, refresh_token)


@router.post("/logout", response_model=MessageOut, summary="Revoke the current session")
@limiter.limit("30/minute")
def logout(request: Request, payload: LogoutIn, db: DbSession) -> MessageOut:
    auth_service.revoke_refresh_token(db, payload.refresh_token)
    return MessageOut(message="You have been signed out.")


@router.post("/logout-all", response_model=MessageOut, summary="Revoke every session")
def logout_all(current_user: CurrentUser, db: DbSession) -> MessageOut:
    auth_service.revoke_all_sessions(db, current_user.id)
    return MessageOut(message="Signed out from all devices.")


@router.get("/me", response_model=UserMeOut, summary="Current account")
def me(current_user: CurrentUser) -> UserMeOut:
    return UserMeOut.model_validate(current_user)


@router.post(
    "/forgot-password",
    response_model=MessageOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password-reset link",
    description="Always returns 202 so the endpoint cannot be used to discover registered emails.",
)
@limiter.limit("3/minute")
def forgot_password(request: Request, payload: ForgotPasswordIn, db: DbSession) -> MessageOut:
    auth_service.request_password_reset(db, str(payload.email))
    return MessageOut(
        message="If this email is registered, a reset link has been sent.",
        detail=None if settings.smtp_configured else "Email delivery is not configured; the link is written to the server log.",
    )


@router.post("/reset-password", response_model=MessageOut, summary="Set a new password")
@limiter.limit("5/minute")
def reset_password(request: Request, payload: ResetPasswordIn, db: DbSession) -> MessageOut:
    auth_service.reset_password(db, payload.token, payload.new_password)
    return MessageOut(message="Password updated. Please sign in with your new password.")


@router.post("/change-password", response_model=MessageOut, summary="Change password (signed in)")
def change_password(payload: ChangePasswordIn, current_user: CurrentUser, db: DbSession) -> MessageOut:
    auth_service.change_password(db, current_user, payload.current_password, payload.new_password)
    return MessageOut(message="Password changed. Other devices were signed out.")


@router.post(
    "/verify-email",
    response_model=UserMeOut,
    summary="Confirm an email address",
    description="Consumes the single-use token from the confirmation email.",
)
def verify_email(payload: VerifyEmailIn, db: DbSession) -> UserMeOut:
    user = auth_service.verify_email(db, payload.token)
    return UserMeOut.model_validate(user)


@router.post("/resend-verification", response_model=MessageOut, status_code=202, summary="Resend the confirmation email")
@limiter.limit("3/minute")
def resend_verification(request: Request, current_user: CurrentUser, db: DbSession) -> MessageOut:
    auth_service.resend_verification_email(db, current_user)
    return MessageOut(message="Confirmation email sent.")
