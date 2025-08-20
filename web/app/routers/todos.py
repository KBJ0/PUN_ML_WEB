# app/routers/todos.py
from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from sqlalchemy.orm import Session
from app.db import get_db
from app import crud, schemas
from app.models import User

router = APIRouter(prefix="/api/todos", tags=["todos"])

def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="Login required")
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user

@router.get("/", response_model=list[schemas.TodoRead])
def list_all(user: User = Depends(require_login), db: Session = Depends(get_db)):
    return crud.list_todos(db, user_id=user.id)

@router.post("/", response_model=schemas.TodoRead, status_code=status.HTTP_201_CREATED)
def create(payload: schemas.TodoCreate, response: Response,
           user: User = Depends(require_login), db: Session = Depends(get_db)):
    todo = crud.create_todo(db, payload.title, user_id=user.id)
    response.headers["Location"] = f"/api/todos/{todo.id}"
    return todo

@router.get("/{todo_id}", response_model=schemas.TodoRead)
def retrieve(todo_id: int, user: User = Depends(require_login), db: Session = Depends(get_db)):
    todo = crud.get_todo(db, todo_id, user_id=user.id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo

@router.patch("/{todo_id}", response_model=schemas.TodoRead)
def partial_update(todo_id: int, payload: schemas.TodoUpdate,
                   user: User = Depends(require_login), db: Session = Depends(get_db)):
    todo = crud.get_todo(db, todo_id, user_id=user.id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return crud.update_todo(db, todo, title=payload.title, is_done=payload.is_done)

@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(todo_id: int, user: User = Depends(require_login), db: Session = Depends(get_db)):
    todo = crud.get_todo(db, todo_id, user_id=user.id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    crud.delete_todo(db, todo)
    return Response(status_code=204)
