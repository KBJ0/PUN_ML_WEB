from pathlib import Path
import secrets
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User
from app.security import (
    verify_password, hash_password, create_user, find_user_by_identifier,
    issue_reset_token, send_reset_email, consume_reset_token
)

router = APIRouter(prefix="/auth", tags=["auth"])
BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def _csrf(request: Request) -> str:
    t = secrets.token_urlsafe(32)
    request.session["csrf"] = t
    return t

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "csrf_token": _csrf(request), "title": "로그인"},
    )

@router.post("/login")
def login(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    if csrf_token != request.session.pop("csrf", None):
        raise HTTPException(400, "Invalid CSRF")
    user = find_user_by_identifier(db, identifier)
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "아이디/비번이 올바르지 않습니다.", "csrf_token": _csrf(request)},
            status_code=400,
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)

@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)

@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "csrf_token": _csrf(request), "title": "회원가입"},
    )

@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    if csrf_token != request.session.pop("csrf", None):
        raise HTTPException(400, "Invalid CSRF")
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "이미 존재하는 아이디", "csrf_token": _csrf(request)},
            status_code=400,
        )
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "이미 가입된 이메일", "csrf_token": _csrf(request)},
            status_code=400,
        )
    create_user(db, username=username, email=email, password=password)
    return RedirectResponse("/auth/login", status_code=303)

@router.get("/forgot", response_class=HTMLResponse)
def forgot_form(request: Request):
    return templates.TemplateResponse(
        "forgot.html",
        {"request": request, "csrf_token": _csrf(request), "title": "비밀번호 찾기"},
    )

@router.post("/forgot")
def forgot(
    request: Request,
    email: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    if csrf_token != request.session.pop("csrf", None):
        raise HTTPException(400, "Invalid CSRF")
    user = db.query(User).filter(User.email == email).first()
    # 존재 여부와 무관하게 동일 응답(열거 방지)
    if user:
        token = issue_reset_token(db, user)
        send_reset_email(user, token)        # ✅ User 객체를 전달 (핵심 수정)
    return templates.TemplateResponse(
        "forgot_done.html", {"request": request, "title": "이메일을 확인하세요"}
    )

@router.get("/reset/{token}", response_class=HTMLResponse)
def reset_form(token: str, request: Request):
    return templates.TemplateResponse(
        "reset.html",
        {"request": request, "csrf_token": _csrf(request), "title": "비밀번호 재설정", "token": token},
    )

@router.post("/reset/{token}")
def reset(
    token: str,
    request: Request,
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    if csrf_token != request.session.pop("csrf", None):
        raise HTTPException(400, "Invalid CSRF")
    user = consume_reset_token(db, token)
    if not user:
        return templates.TemplateResponse(
            "reset.html",
            {"request": request, "error": "토큰이 만료되었거나 올바르지 않습니다.", "csrf_token": _csrf(request), "token": token},
            status_code=400,
        )
    user.password_hash = hash_password(password)
    db.add(user)
    db.commit()
    return RedirectResponse("/auth/login", status_code=303)
