# app/crud.py
from sqlalchemy.orm import Session
from app import models

def list_todos(db: Session, user_id: int):
    return (db.query(models.Todo)
              .filter(models.Todo.user_id == user_id)
              .order_by(models.Todo.id.desc())
              .all())

def get_todo(db: Session, todo_id: int, user_id: int):
    return (db.query(models.Todo)
              .filter(models.Todo.id == todo_id, models.Todo.user_id == user_id)
              .first())

def create_todo(db: Session, title: str, user_id: int):
    todo = models.Todo(title=title, user_id=user_id)
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo

def update_todo(db: Session, todo: models.Todo, *, title=None, is_done=None):
    if title is not None:
        todo.title = title
    if is_done is not None:
        todo.is_done = is_done
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo

def delete_todo(db: Session, todo: models.Todo):
    db.delete(todo)
    db.commit()
