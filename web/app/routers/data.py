# app/routers/data.py
# (상단 import 및 다른 함수들은 모두 그대로 유지)
from __future__ import annotations
from pathlib import Path
import os, uuid, math, io
import logging
import aiofiles
import chardet
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sentence_transformers import SentenceTransformer
from category_encoders import TargetEncoder
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, DataFile, TrainedModel
from app import schemas

# (router, logger, 유틸, CSV 로더, 프로파일링, 업로드, 전처리 함수는 이전과 동일)
router = APIRouter(prefix="/data", tags=["data"])
BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
logger = logging.getLogger("app.data")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(h)


def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("user_id")
    if not uid: raise HTTPException(status_code=401, detail="Login required")
    user = db.get(User, uid)
    if not user: raise HTTPException(status_code=401, detail="Login required")
    return user


def get_storage_dir() -> Path:
    root = Path(os.getenv("STORAGE_DIR") or (BASE_DIR.parent / "storage"))
    for sub in ["original", "processed", "models"]:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def human_size(n: int) -> str:
    if n <= 0: return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(n, 1024)))
    return f"{n / (1024 ** i):.1f} {units[i]}"


def _read_with_params_csv(path: Path, enc: str, strict: bool, sep=None) -> pd.DataFrame:
    kwargs = dict(engine="python", sep=sep)
    if "encoding_errors" in pd.read_csv.__code__.co_varnames:
        return pd.read_csv(path, encoding=enc, encoding_errors=("strict" if strict else "replace"), **kwargs)
    text = path.read_bytes().decode(enc, errors=("strict" if strict else "replace"))
    return pd.read_csv(io.StringIO(text), **kwargs)


def read_csv_robust(path: Path, hint: str | None = None) -> tuple[pd.DataFrame, str, list[str]]:
    tried: list[str] = []
    last_err: Exception | None = None

    def try_order(order: list[str], label: str):
        nonlocal tried, last_err
        for enc in order:
            enc_norm = enc.lower()
            if enc_norm in tried: continue
            for strict in (True, False):
                mode = "strict" if strict else "replace"
                try:
                    df = _read_with_params_csv(path, enc, strict, sep=None)
                    if df.shape[1] == 1:
                        df_tab = _read_with_params_csv(path, enc, strict, sep="\t")
                        if df_tab.shape[1] > 1: df = df_tab
                    used = enc if strict else f"{enc} (lossy)"
                    return df, used
                except Exception as e:
                    last_err = e
            tried.append(enc_norm)
        return None

    encodings_to_try = []
    if hint and hint.lower() not in ("", "auto", "자동"): encodings_to_try.append(hint)
    encodings_to_try.extend(guess_encodings(path))
    if r := try_order(list(dict.fromkeys(encodings_to_try)), "candidates"): return *r, tried
    raise RuntimeError(f"CSV 디코딩 실패 (마지막 오류: {last_err})")


def guess_encodings(path: Path) -> list[str]:
    raw = path.read_bytes()[:200_000]
    det = chardet.detect(raw)
    enc = (det.get("encoding") or "").lower()
    cands: list[str] = []
    if enc:
        if enc == "ascii":
            enc = "utf-8"
        elif "euc" in enc or "kr" in enc:
            enc = "cp949"
        cands.append(enc)
    common = ["cp949", "utf-8", "utf-8-sig", "euc-kr"]
    cands.extend(x for x in common if x not in cands)
    return cands


def profile_dataframe(df: pd.DataFrame) -> dict:
    def auto_convert_numeric(df_to_convert: pd.DataFrame):
        for col in df_to_convert.select_dtypes(include="object").columns:
            if df_to_convert[col].isnull().all(): continue
            try:
                series_no_comma = df_to_convert[col].str.replace(',', '', regex=False)
                converted_series = pd.to_numeric(series_no_comma, errors='coerce')
                original_notna_count = df_to_convert[col].notna().sum()
                if original_notna_count > 0 and (converted_series.notna().sum() / original_notna_count) >= 0.95:
                    df_to_convert[col] = converted_series
            except Exception:
                continue

    def auto_parse_datetime(df_to_parse: pd.DataFrame):
        sample_df = df_to_parse.head(min(len(df_to_parse), 1000))
        for c in df_to_parse.columns:
            if df_to_parse[c].dtype == "object":
                try:
                    if pd.to_datetime(sample_df[c], errors="coerce").notna().mean() >= 0.8:
                        df_to_parse[c] = pd.to_datetime(df_to_parse[c], errors="coerce")
                except Exception:
                    continue

    auto_convert_numeric(df)
    auto_parse_datetime(df)
    n_rows, n_cols = df.shape
    return {"n_rows": int(n_rows), "n_cols": int(n_cols),
            "numeric_cols": [str(c) for c in df.select_dtypes(include="number").columns],
            "categorical_cols": [str(c) for c in df.select_dtypes(include=["object", "category"]).columns],
            "datetime_cols": [str(c) for c in
                              df.select_dtypes(include=["datetime", "datetimetz", "datetime64[ns]"]).columns],
            "bool_cols": [str(c) for c in df.select_dtypes(include="bool").columns],
            "missing_cols": [str(c) for c in df.columns if df[c].isna().any()],
            "column_types": {str(c): str(df[c].dtype) for c in df.columns}, }


@router.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request, user: User = Depends(require_login)):
    return templates.TemplateResponse("data_upload.html", {"request": request, "title": "데이터 업로드"})


@router.post("/upload", response_class=HTMLResponse)
async def handle_upload(request: Request, file: UploadFile = File(...), encoding_hint: str | None = Form(None),
                        user: User = Depends(require_login), db: Session = Depends(get_db)):
    ext = Path(file.filename).suffix.lower()
    if ext not in {".csv", ".xlsx"}: return templates.TemplateResponse("data_upload.html", {"request": request,
                                                                                            "error": "CSV 또는 XLSX만 업로드 가능합니다."},
                                                                       status_code=400)
    storage = get_storage_dir()
    dest = storage / "original" / f"{uuid.uuid4().hex}{ext}"
    async with aiofiles.open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024): await out.write(chunk)
    size_bytes = dest.stat().st_size
    tried = []
    try:
        if ext == ".csv":
            df, encoding_used, tried = read_csv_robust(dest, hint=encoding_hint)
        else:
            df, encoding_used = pd.read_excel(dest, engine="openpyxl"), "excel"
    except Exception as e:
        dest.unlink(missing_ok=True)
        return templates.TemplateResponse("data_upload.html",
                                          {"request": request, "error": f"파일 읽기 실패: {e}", "tried": tried},
                                          status_code=500)
    prof = profile_dataframe(df)
    data = DataFile(user_id=user.id, original_filename=file.filename, stored_path=str(dest), file_ext=ext.lstrip("."),
                    encoding=encoding_used, size_bytes=size_bytes, n_rows=prof["n_rows"], n_cols=prof["n_cols"],
                    column_types=prof["column_types"], profile={**prof, "size_human": human_size(size_bytes)})
    db.add(data);
    db.commit();
    db.refresh(data)
    return templates.TemplateResponse("data_profile.html", {"request": request, "data": data, "profile": data.profile})


@router.get("/{data_id}", response_class=HTMLResponse)
def view_profile(data_id: int, request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    data = db.get(DataFile, data_id)
    if not data or data.user_id != user.id: raise HTTPException(status_code=404)
    return templates.TemplateResponse("data_profile.html", {"request": request, "data": data, "profile": data.profile})


@router.post("/{data_id}/preprocess", response_class=HTMLResponse)
async def handle_preprocess(data_id: int, config: schemas.PreprocessingConfig, request: Request,
                            user: User = Depends(require_login), db: Session = Depends(get_db)):
    try:
        original_datafile = db.get(DataFile, data_id)
        if not original_datafile or original_datafile.user_id != user.id: raise HTTPException(status_code=404)
        df = pd.read_csv(Path(original_datafile.stored_path), encoding=original_datafile.encoding or 'utf-8-sig')
        profile_dataframe(df)
        if config.row_limit: df = df.head(config.row_limit)
        if config.new_column_rules:
            for rule in config.new_column_rules:
                try:
                    df[rule.name] = df.eval(rule.formula, engine='python')
                except Exception as e:
                    logger.error(f"새 컬럼 '{rule.name}' 추가 실패: {e}")
        bool_cols = df.select_dtypes(include="bool").columns
        if not bool_cols.empty: df[bool_cols] = df[bool_cols].astype(int)
        if config.missing_value_rules:
            for rule in config.missing_value_rules:
                if rule.column in df.columns:
                    if rule.method == "fill_zero":
                        df[rule.column] = df[rule.column].fillna(0)
                    elif rule.method == "drop_row":
                        df = df.dropna(subset=[rule.column])
        if config.filter_contains_rules:
            for rule in config.filter_contains_rules:
                if rule.column in df.columns and pd.api.types.is_string_dtype(df[rule.column]):
                    df = df[~df[rule.column].str.contains(rule.keyword, na=False)]
        if config.numeric_filter_rules:
            for rule in config.numeric_filter_rules:
                if rule.column in df.columns:
                    try:
                        query_str = f"`{rule.column}` {rule.operator} {rule.value}"
                        df = df.query(f"not ({query_str})")
                    except Exception as e:
                        logger.error(f"수치형 필터링 실패 ('{rule.column}'): {e}")
        if config.drop_columns:
            cols_to_drop = [col for col in config.drop_columns if col in df.columns]
            if cols_to_drop: df = df.drop(columns=cols_to_drop)
        storage = get_storage_dir()
        processed_filename = f"{Path(original_datafile.stored_path).stem}_processed.csv"
        processed_path = storage / "processed" / processed_filename
        df.to_csv(processed_path, index=False, encoding='utf-8-sig')
        processed_prof = profile_dataframe(df)
        processed_datafile = DataFile(user_id=user.id,
                                      original_filename=f"[Processed] {original_datafile.original_filename}",
                                      stored_path=str(processed_path), is_processed=True,
                                      original_file_id=original_datafile.id, file_ext='csv',
                                      size_bytes=processed_path.stat().st_size, n_rows=processed_prof["n_rows"],
                                      n_cols=processed_prof["n_cols"], column_types=processed_prof["column_types"],
                                      profile=processed_prof)
        db.add(processed_datafile);
        db.commit()
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        logger.error(f"전처리 중 오류: {e}", exc_info=True)
        return HTMLResponse(f"<h1>전처리 중 오류 발생</h1><p>{e}</p>", status_code=500)


@router.get("/{data_id}/select-model", response_class=HTMLResponse)
def select_model_form(data_id: int, request: Request, user: User = Depends(require_login),
                      db: Session = Depends(get_db)):
    datafile = db.get(DataFile, data_id)
    if not datafile or datafile.user_id != user.id or not datafile.is_processed: raise HTTPException(status_code=404)
    df = pd.read_csv(Path(datafile.stored_path))
    numeric_cols = df.select_dtypes(include='number').columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    cardinality = {col: df[col].nunique() for col in categorical_cols}
    return templates.TemplateResponse("model_selection.html",
                                      {"request": request, "title": "모델 학습 설정", "datafile": datafile,
                                       "processed_shape": f"{df.shape[0]}행 x {df.shape[1]}열",
                                       "processed_path": datafile.stored_path,
                                       "df_preview": df.head(50).to_html(classes='table', border=0, index=False),
                                       "numeric_cols": numeric_cols, "categorical_cols": categorical_cols,
                                       "cardinality": cardinality})


# --- 👇 이 함수를 교체하세요 ---
@router.post("/train", response_class=HTMLResponse)
async def handle_train(config: schemas.ModelTrainConfig, request: Request, user: User = Depends(require_login),
                       db: Session = Depends(get_db)):
    try:
        df = pd.read_csv(config.processed_file_path)
        y = df[config.target_column]

        feature_info = {
            'numeric': config.numeric_features or [],
            'onehot': config.one_hot_encode_features or [],
            'target': config.target_encode_features or [],
            'sentence': config.sentence_embedding_features or [],
        }
        feature_cols = feature_info['numeric'] + feature_info['onehot'] + feature_info['target'] + feature_info[
            'sentence']
        X = df[feature_cols]

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        parts_train, parts_test, fitted_objects = [], [], {'feature_info': feature_info}

        if feature_info['numeric']:
            parts_train.append(X_train[feature_info['numeric']].reset_index(drop=True))
            parts_test.append(X_test[feature_info['numeric']].reset_index(drop=True))
        if feature_info['onehot']:
            encoder = pd.get_dummies(X_train[feature_info['onehot']], drop_first=True, dummy_na=True)
            parts_train.append(encoder.reset_index(drop=True))
            parts_test.append(
                pd.get_dummies(X_test[feature_info['onehot']], dummy_na=True).reindex(columns=encoder.columns,
                                                                                      fill_value=0).reset_index(
                    drop=True))
            fitted_objects['onehot_columns'] = encoder.columns.tolist()
        if feature_info['target']:
            encoder = TargetEncoder(cols=feature_info['target'], handle_missing='value', handle_unknown='value')
            encoder.fit(X_train[feature_info['target']], y_train)
            parts_train.append(encoder.transform(X_train[feature_info['target']]).reset_index(drop=True))
            parts_test.append(encoder.transform(X_test[feature_info['target']]).reset_index(drop=True))
            fitted_objects['target_encoder'] = encoder
        if feature_info['sentence']:
            model_name = 'paraphrase-multilingual-MiniLM-L12-v2'
            sbert_model = SentenceTransformer(model_name)
            for col in feature_info['sentence']:
                train_emb = pd.DataFrame(sbert_model.encode(X_train[col].astype(str).fillna('').tolist())).add_prefix(
                    f'{col}_emb_')
                test_emb = pd.DataFrame(sbert_model.encode(X_test[col].astype(str).fillna('').tolist())).add_prefix(
                    f'{col}_emb_')
                parts_train.append(train_emb.reset_index(drop=True))
                parts_test.append(test_emb.reset_index(drop=True))
            fitted_objects['sbert_model_name'] = model_name

        X_train_final, X_test_final = pd.concat(parts_train, axis=1), pd.concat(parts_test, axis=1)
        X_train_final.columns = ["".join(c if c.isalnum() else "_" for c in str(x)) for x in X_train_final.columns]
        X_test_final.columns = X_train_final.columns

        model = xgb.XGBRegressor(objective='reg:squarederror', n_estimators=100, random_state=42)
        model.fit(X_train_final, y_train)
        preds = model.predict(X_test_final)

        rmse, mae, r2 = np.sqrt(mean_squared_error(y_test, preds)), mean_absolute_error(y_test, preds), r2_score(y_test,
                                                                                                                 preds)

        storage = get_storage_dir()
        model_name = f"xgb_{config.target_column}_{uuid.uuid4().hex[:8]}"
        model_path = storage / "models" / f"{model_name}.joblib"
        fitted_objects.update({'model': model, 'final_feature_names': X_train_final.columns.tolist()})
        joblib.dump(fitted_objects, model_path)

        new_model = TrainedModel(user_id=user.id, model_name=model_name, model_path=str(model_path),
                                 source_datafile_id=config.source_datafile_id, feature_info=feature_info, rmse=rmse,
                                 mae=mae, r2=r2)
        db.add(new_model);
        db.commit()

        return templates.TemplateResponse("train_result.html",
                                          {"request": request, "title": "학습 완료", "model_name": model_name,
                                           "model_path": str(model_path),
                                           "performance": {"RMSE": f"{rmse:.4f}", "MAE": f"{mae:.4f}",
                                                           "R2": f"{r2:.4f}"}})
    except Exception as e:
        logger.error(f"모델 학습 중 오류: {e}", exc_info=True)
        return HTMLResponse(f"<h1>모델 학습 중 오류 발생</h1><p>{e}</p>", status_code=500)


@router.get("/models/{model_id}/predict", response_class=HTMLResponse)
def predict_form(model_id: int, request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    model_info = db.get(TrainedModel, model_id)
    if not model_info or model_info.user_id != user.id: raise HTTPException(status_code=404)
    return templates.TemplateResponse("predict_form.html", {"request": request, "title": "모델 예측", "model": model_info,
                                                            "feature_info": model_info.feature_info})


@router.post("/models/{model_id}/predict-manual", response_class=HTMLResponse)
async def handle_predict_manual(model_id: int, request: Request, user: User = Depends(require_login),
                                db: Session = Depends(get_db)):
    model_info = db.get(TrainedModel, model_id)
    if not model_info or model_info.user_id != user.id: raise HTTPException(status_code=404)

    form_data = await request.form()
    input_df = pd.DataFrame([form_data])

    model_bundle = joblib.load(model_info.model_path)
    model = model_bundle['model']
    feature_info = model_bundle['feature_info']
    final_feature_names = model_bundle['final_feature_names']

    processed_parts = []

    if numeric_cols := feature_info.get('numeric'):
        numeric_df = input_df[numeric_cols].apply(pd.to_numeric, errors='coerce')
        processed_parts.append(numeric_df.reset_index(drop=True))
    if onehot_cols := feature_info.get('onehot'):
        onehot_df = pd.get_dummies(input_df[onehot_cols], dummy_na=True).reindex(columns=model_bundle['onehot_columns'],
                                                                                 fill_value=0)
        processed_parts.append(onehot_df.reset_index(drop=True))
    if target_cols := feature_info.get('target'):
        encoder = model_bundle['target_encoder']
        target_df = encoder.transform(input_df[target_cols])
        processed_parts.append(target_df.reset_index(drop=True))
    if sentence_cols := feature_info.get('sentence'):
        sbert = SentenceTransformer(model_bundle['sbert_model_name'])
        for col in sentence_cols:
            embeddings = sbert.encode(input_df[col].astype(str).fillna('').tolist())
            emb_df = pd.DataFrame(embeddings).add_prefix(f'{col}_emb_')
            processed_parts.append(emb_df.reset_index(drop=True))

    final_input = pd.concat(processed_parts, axis=1)
    final_input.columns = ["".join(c if c.isalnum() else "_" for c in str(x)) for x in final_input.columns]
    final_input = final_input.reindex(columns=final_feature_names, fill_value=0)

    prediction = model.predict(final_input)[0]

    return templates.TemplateResponse("predict_result.html", {"request": request, "title": "예측 결과", "model": model_info,
                                                              "prediction": prediction})


@router.post("/models/{model_id}/predict-file", response_class=HTMLResponse)
async def handle_predict_file(model_id: int, request: Request, file: UploadFile = File(...),
                              user: User = Depends(require_login), db: Session = Depends(get_db)):
    model_info = db.get(TrainedModel, model_id)
    if not model_info or model_info.user_id != user.id: raise HTTPException(status_code=404)
    df_pred = pd.read_csv(file.file)
    input_df = df_pred.copy()

    model_bundle = joblib.load(model_info.model_path)
    model = model_bundle['model']
    feature_info = model_bundle['feature_info']
    final_feature_names = model_bundle['final_feature_names']

    processed_parts = []

    if numeric_cols := feature_info.get('numeric'):
        numeric_df = input_df[numeric_cols].apply(pd.to_numeric, errors='coerce')
        processed_parts.append(numeric_df.reset_index(drop=True))
    if onehot_cols := feature_info.get('onehot'):
        onehot_df = pd.get_dummies(input_df[onehot_cols], dummy_na=True).reindex(columns=model_bundle['onehot_columns'],
                                                                                 fill_value=0)
        processed_parts.append(onehot_df.reset_index(drop=True))
    if target_cols := feature_info.get('target'):
        encoder = model_bundle['target_encoder']
        target_df = encoder.transform(input_df[target_cols])
        processed_parts.append(target_df.reset_index(drop=True))
    if sentence_cols := feature_info.get('sentence'):
        sbert = SentenceTransformer(model_bundle['sbert_model_name'])
        for col in sentence_cols:
            embeddings = sbert.encode(input_df[col].astype(str).fillna('').tolist())
            emb_df = pd.DataFrame(embeddings).add_prefix(f'{col}_emb_')
            processed_parts.append(emb_df.reset_index(drop=True))

    final_input = pd.concat(processed_parts, axis=1)
    final_input.columns = ["".join(c if c.isalnum() else "_" for c in str(x)) for x in final_input.columns]
    final_input = final_input.reindex(columns=final_feature_names, fill_value=0)

    predictions = model.predict(final_input)
    df_pred['prediction'] = predictions

    return templates.TemplateResponse("predict_result.html", {"request": request, "title": "예측 결과", "model": model_info,
                                                              "predictions_df_html": df_pred.to_html(classes='table',
                                                                                                     index=False)})
