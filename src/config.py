import os
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
CHUNK_SIZE = 2000  # tokens
CHUNK_OVERLAP = 0  # 章节边界感知，不重叠
CHROMA_PERSIST_DIR = "./chroma_data"
OUTPUT_DIR = "./output"
UPLOAD_DIR = "./uploads"
