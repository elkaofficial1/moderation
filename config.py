import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
MODERATOR_ID = int(os.getenv("MODERATOR_ID", os.getenv("ADMIN_ID", "0")))
AI_URL = os.getenv("AI_URL", "http://127.0.0.1:11434/api/chat")
MODEL = os.getenv("MODEL", "qwen2.5:3b")
OBSERVE_MODE = os.getenv("OBSERVE_MODE", "true").lower() == "true"
AUTO_BAN = os.getenv("AUTO_BAN", "false").lower() == "true"
MAX_CONTEXT_MESSAGES = int(os.getenv("MAX_CONTEXT_MESSAGES", "10"))
TEST_JSON_LIMIT = int(os.getenv("TEST_JSON_LIMIT", "1000"))
