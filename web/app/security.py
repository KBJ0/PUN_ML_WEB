# app/security.py
import os, secrets, hashlib, smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.models import User, PasswordReset

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(pw: str) -> str:
    return pwd_context.hash(pw)

def verify_password(pw: str, hashed: str) -> bool:
    return pwd_context.verify(pw, hashed)

# --- 👇 여기가 핵심 수정 부분입니다 ---
def create_user(db: Session, *, username: str, email: str, password: str) -> User:
    # User 모델에 없는 'condition=True' 인자를 삭제했습니다.
    u = User(username=username, email=email, password_hash=hash_password(password))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u
# ------------------------------------

def find_user_by_identifier(db: Session, identifier: str) -> User | None:
    return db.query(User).filter((User.username == identifier) | (User.email == identifier)).first()

def issue_reset_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    db.add(PasswordReset(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db.commit()
    return token

def consume_reset_token(db: Session, token: str) -> User | None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    pr = db.query(PasswordReset).filter(
        PasswordReset.token_hash == token_hash,
        PasswordReset.used_at.is_(None),
        PasswordReset.expires_at > now
    ).first()
    if not pr:
        return None
    pr.used_at = now
    db.add(pr); db.commit()
    return db.get(User, pr.user_id)

def send_reset_email(user: User, token: str):
    base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
    url = f"{base_url}/auth/reset/{token}"
    text = (
        f"가입한 ID: {user.username}\n"
        f"비밀번호: 1시간 내 아래 링크로 재설정하세요.\n"
        f"{url}\n"
    )
    html = f"""
    <!doctype html>
    <html><body>
      <p>
        가입한 ID: <b>{user.username}</b><br>
        비밀번호: 1시간 내 아래 링크로 재설정하세요.<br>
        <a href="{url}">링크</a>
      </p>
    </body></html>
    """
    msg = EmailMessage()
    msg["Subject"] = "비밀번호 재설정 안내"
    msg["From"] = os.getenv("EMAIL_FROM")
    msg["To"] = user.email
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pw = os.getenv("SMTP_PASSWORD")
    with smtplib.SMTP_SSL(host, port) as s:
        if smtp_user:
            s.login(smtp_user, smtp_pw)
        s.send_message(msg)
