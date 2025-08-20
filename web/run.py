# run.py
import uvicorn
from dotenv import load_dotenv
from pathlib import Path
import os

if __name__ == "__main__":
    # 1. .env 파일의 경로를 명확히 지정하고 로드합니다.
    env_path = Path('app') / '.env'
    print(f"--- Attempting to load .env file from: {env_path.resolve()} ---")

    if not env_path.exists():
        print(f"!!! ERROR: .env file not found at the location above.")
        print("!!! Please make sure the .env file is in the 'web' folder.")
    else:
        load_dotenv(dotenv_path=env_path)
        print("--- .env file found. Checking variables... ---")

        # 2. 환경 변수가 제대로 로드되었는지 즉시 확인합니다.
        db_url = os.getenv("DATABASE_URL")
        secret_key = os.getenv("SECRET_KEY")

        if db_url:
            print("--- SUCCESS: DATABASE_URL loaded successfully.")
        else:
            print("!!! ERROR: DATABASE_URL not found after loading .env. Check the .env file content.")

        if secret_key:
            print("--- SUCCESS: SECRET_KEY loaded successfully.")
        else:
            print("!!! ERROR: SECRET_KEY not found after loading .env. Check the .env file content.")

    # 3. 환경 변수가 로드된 상태에서 Uvicorn을 실행합니다.
    print("\n--- Starting Uvicorn server... ---")
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8001,
        reload=True
    )
