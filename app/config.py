
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv(
    "QDRANT_COLLECTION", "customer_records"
)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_CHAT_MODEL = os.getenv(
    "OLLAMA_CHAT_MODEL", "mistral"
)
OLLAMA_EMBED_MODEL = os.getenv(
    "OLLAMA_EMBED_MODEL", "nomic-embed-text"
)

DEV_OTP_ENABLED = os.getenv("DEV_OTP_ENABLED", "false").lower() == "true"
