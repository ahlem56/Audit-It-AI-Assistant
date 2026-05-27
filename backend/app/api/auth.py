from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from typing import Optional

from app.config.settings import (
    AUTH_COOKIE_SECURE,
    AUTH_FRONTEND_BASE_URL,
    AUTH_SESSION_COOKIE_NAME,
    AUTH_SESSION_TTL_HOURS,
)
from app.models.api_models import (
    AuthConfigResponse,
    AuthSessionResponse,
    AuthUser,
    LogoutResponse,
    UpdateMyProfileRequest,
)
from app.services.auth_service import (
    AuthenticationError,
    AuthConfigurationError,
    begin_entra_login,
    clear_session,
    complete_entra_login,
    delete_my_profile_image,
    get_authenticated_user,
    get_my_profile_image,
    get_auth_public_config,
    get_logout_redirect_url,
    require_authenticated_user,
    save_my_profile_image,
    update_my_profile,
)
from app.services.security_audit_service import log_security_event

router = APIRouter(prefix="/auth")


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config():
    return get_auth_public_config()


@router.get("/me", response_model=AuthSessionResponse)
async def auth_me(request: Request):
    user = get_authenticated_user(request)
    return {
        "authenticated": user is not None,
        "auth_enabled": get_auth_public_config()["enabled"],
        "user": user,
    }


@router.get("/entra/login")
async def entra_login(
    prompt: Optional[str] = Query(default=None),
    next: Optional[str] = Query(default="/"),
):
    try:
        target_url = begin_entra_login(prompt=prompt, next_path=next)
    except AuthConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RedirectResponse(url=target_url, status_code=302)


@router.get("/entra/callback")
async def entra_callback(
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
):
    if error:
        log_security_event(
            action="LOGIN_FAILED",
            request=request,
            status="failure",
            metadata={"error": error, "error_description": error_description or ""},
        )
        failure_url = f"{get_auth_public_config()['logout_url']}?error={urllib.parse.quote(error)}"
        if error_description:
            failure_url = f"{failure_url}&error_description={urllib.parse.quote(error_description)}"
        return RedirectResponse(url=failure_url, status_code=302)

    if not code or not state:
        log_security_event(
            action="LOGIN_FAILED",
            request=request,
            status="failure",
            metadata={"error": "missing_authorization_code_or_state"},
        )
        raise HTTPException(status_code=400, detail="Missing authorization code or state.")

    try:
        user, session_token, next_path = complete_entra_login(
            code=code,
            state_token=state,
            user_agent=request.headers.get("user-agent", ""),
        )
    except (AuthenticationError, AuthConfigurationError) as exc:
        log_security_event(
            action="LOGIN_FAILED",
            request=request,
            status="failure",
            metadata={"error": str(exc)},
        )
        failure_url = (
            f"{get_auth_public_config()['logout_url']}?error=auth_failed"
            f"&error_description={urllib.parse.quote(str(exc))}"
        )
        return RedirectResponse(url=failure_url, status_code=302)

    response = RedirectResponse(url=f"{AUTH_FRONTEND_BASE_URL}{next_path}", status_code=302)
    response.set_cookie(
        key=AUTH_SESSION_COOKIE_NAME,
        value=session_token,
        max_age=AUTH_SESSION_TTL_HOURS * 60 * 60,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    log_security_event(
        action="LOGIN_SUCCESS",
        user=user,
        request=request,
        resource_type="auth_session",
        status="success",
    )
    return response


@router.post("/logout", response_model=LogoutResponse)
async def logout(request: Request):
    session_token = request.cookies.get(AUTH_SESSION_COOKIE_NAME)
    clear_session(session_token)

    response = {
        "logged_out": True,
        "logout_url": get_logout_redirect_url(),
    }
    return response


@router.patch("/me", response_model=AuthUser)
async def patch_my_profile(
    payload: UpdateMyProfileRequest,
    user=Depends(require_authenticated_user),
):
    try:
        return update_my_profile(
            user["user_id"],
            organization=payload.organization,
            job_title=payload.job_title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/me/avatar")
async def get_my_avatar(user=Depends(require_authenticated_user)):
    try:
        content, content_type = get_my_profile_image(user["user_id"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=content, media_type=content_type)


@router.post("/me/avatar", response_model=AuthUser)
async def upload_my_avatar(
    file: UploadFile = File(...),
    user=Depends(require_authenticated_user),
):
    try:
        content = await file.read()
        return save_my_profile_image(
            user["user_id"],
            content=content,
            original_filename=file.filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/me/avatar", response_model=AuthUser)
async def remove_my_avatar(user=Depends(require_authenticated_user)):
    try:
        return delete_my_profile_image(user["user_id"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
