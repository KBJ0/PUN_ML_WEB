# app/config.py
import os

# run.py가 .env 파일을 먼저 로드하므로, 여기서는 이미 설정된 환경 변수를 읽기만 합니다.
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")

# 변수가 없는 경우를 대비한 최종 방어 코드
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found in environment. Did you run the app using 'python run.py'?")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY not found in environment. Did you run the app using 'python run.py'?")
