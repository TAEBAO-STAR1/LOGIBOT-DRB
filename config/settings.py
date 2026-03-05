import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # --- Qdrant 설정 ---
    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
    # URL 형태로 변환 (Retriever 등에서 사용하기 위함)
    QDRANT_URL = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
    
    # --- 컬렉션 이름 ---
    COLLECTION_NAME = os.getenv("COLLECTION_NAME", "logistics_data")
    LEARNING_COLLECTION = os.getenv("LEARNING_COLLECTION", "learning_history")
    BAD_FEEDBACK_COLLECTION = os.getenv("BAD_FEEDBACK_COLLECTION", "bad_feedback_history")

    # --- Ollama 및 임베딩 ---
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "granite-embedding:278m")

    # --- 온프레미스 LLM (Gemma 대신 새 모델 설정 적용) ---
    ONPREMISE_API_URL = os.getenv("ONPREMISE_API_URL", f"http://192.168.1.120:11436/v1/chat/completions")
    ONPREMISE_MODEL = os.getenv("ONPREMISE_MODEL", "openai/gpt-oss-120b")
    ONPREMISE_TIMEOUT = int(os.getenv("ONPREMISE_TIMEOUT", 60))

    # --- 성능 및 최적화 ---
    MAX_WORKERS = int(os.getenv("MAX_WORKERS", 4))
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", 100))
    CACHE_TTL = int(os.getenv("CACHE_TTL", 300))
    API_RATE_LIMIT = float(os.getenv("API_RATE_LIMIT", 1.0))

    # --- 이메일 알림 설정 ---
    EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # 앱 비밀번호 사용 권장
    EMAIL_FROM = os.getenv("EMAIL_FROM", "")
    EMAIL_TO = os.getenv("EMAIL_TO", "")
    

# 인스턴스화하여 다른 모듈에서 'from config.settings import settings'로 사용
settings = Settings()