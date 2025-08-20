# app/models.py
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, Boolean, DateTime, func, ForeignKey, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


# (기존 Todo, User, PasswordReset, DataFile 모델은 그대로 유지)
class Todo(Base):
    __tablename__ = "todos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    user: Mapped["User | None"] = relationship(back_populates="todos")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resets: Mapped[List["PasswordReset"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    todos: Mapped[List["Todo"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    data_files: Mapped[List["DataFile"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    trained_models: Mapped[List["TrainedModel"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped["User"] = relationship(back_populates="resets")


class DataFile(Base):
    __tablename__ = "data_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    original_file_id: Mapped[int | None] = mapped_column(ForeignKey("data_files.id"), nullable=True)
    file_ext: Mapped[str] = mapped_column(String(10), nullable=False)
    encoding: Mapped[str | None] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    n_rows: Mapped[int | None] = mapped_column(Integer)
    n_cols: Mapped[int | None] = mapped_column(Integer)
    column_types: Mapped[dict | None] = mapped_column(JSON)
    profile: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    owner: Mapped["User"] = relationship(back_populates="data_files")


class TrainedModel(Base):
    __tablename__ = "trained_models"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_path: Mapped[str] = mapped_column(String(500), nullable=False)
    source_datafile_id: Mapped[int] = mapped_column(ForeignKey("data_files.id"))
    feature_info: Mapped[dict | None] = mapped_column(JSON)
    rmse: Mapped[float | None] = mapped_column(Float)
    mae: Mapped[float | None] = mapped_column(Float)
    r2: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    owner: Mapped["User"] = relationship(back_populates="trained_models")

    # --- 👇 원본 데이터 파일과의 관계 설정 추가 ---
    source_datafile: Mapped["DataFile"] = relationship()
