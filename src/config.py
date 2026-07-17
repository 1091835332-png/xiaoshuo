import os
import sys

# 打包后不存在 .env，静默跳过
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
CHUNK_SIZE = 2000  # tokens
CHUNK_OVERLAP = 0  # 章节边界感知，不重叠
CHROMA_PERSIST_DIR = "./chroma_data"
OUTPUT_DIR = "./output"
UPLOAD_DIR = "./uploads"

# PyInstaller 打包后，数据目录对用户可见，放在 exe 同级
if getattr(sys, "frozen", False):
    _exe_dir = os.path.dirname(sys.executable)
    CHROMA_PERSIST_DIR = os.path.join(_exe_dir, "chroma_data")
    OUTPUT_DIR = os.path.join(_exe_dir, "output")
    UPLOAD_DIR = os.path.join(_exe_dir, "uploads")
