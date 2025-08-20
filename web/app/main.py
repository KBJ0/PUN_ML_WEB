# app/main.py
from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, joinedload
from app.config import SECRET_KEY
from app.db import Base, engine, get_db
from app.models import DataFile, TrainedModel
from app.routers import todos as todos_router
from app.routers import auth as auth_router
from app.routers import data as data_router
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="My App")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


app.include_router(auth_router.router)
app.include_router(data_router.router)
app.include_router(todos_router.router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    files = []
    models = []
    if user_id:
        files = db.query(DataFile).filter(DataFile.user_id == user_id).order_by(DataFile.id.desc()).all()
        # --- 👇 joinedload를 사용하여 연관된 source_datafile도 함께 조회 ---
        models = (
            db.query(TrainedModel)
            .options(joinedload(TrainedModel.source_datafile))
            .filter(TrainedModel.user_id == user_id)
            .order_by(TrainedModel.id.desc())
            .all()
        )

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "홈", "files": files, "models": models}
    )
