# app/schemas.py
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

# ----------------------
# Todo 스키마 (기존 그대로)
# ----------------------
class TodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)

class TodoUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    is_done: Optional[bool] = None

class TodoRead(BaseModel):
    id: int
    title: str
    is_done: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ----------------------
# 전처리 규칙 스키마 (업그레이드)
# ----------------------
class MissingValueRule(BaseModel):
    column: str
    method: str = Field(pattern="^(fill_zero|drop_row)$")

class FilterContainsRule(BaseModel):
    column: str
    keyword: str

class NewColumnRule(BaseModel):
    name: str
    formula: str

class NumericFilterRule(BaseModel):
    column: str
    operator: str  # 예: "==", ">", "<", ">=", "<=", "!="
    value: float

class PreprocessingConfig(BaseModel):
    row_limit: Optional[int] = Field(None, gt=0)
    drop_columns: Optional[List[str]] = None
    new_column_rules: Optional[List[NewColumnRule]] = None
    missing_value_rules: Optional[List[MissingValueRule]] = None
    filter_contains_rules: Optional[List[FilterContainsRule]] = None
    numeric_filter_rules: Optional[List[NumericFilterRule]] = None


# ----------------------
# 모델 학습 설정 스키마
# ----------------------
class ModelTrainConfig(BaseModel):
    processed_file_path: str
    source_datafile_id: int
    target_column: str
    numeric_features: List[str]
    one_hot_encode_features: Optional[List[str]] = None
    target_encode_features: Optional[List[str]] = None
    sentence_embedding_features: Optional[List[str]] = None
    model_type: str = "xgboost"
