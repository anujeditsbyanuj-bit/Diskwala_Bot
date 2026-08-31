import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
SESSION = os.environ["SESSION"]
OWNER_ID = int(os.environ["OWNER_ID"])

TG_BOT_WORKERS = int(os.getenv("TG_BOT_WORKERS", "4"))
DOWNLOAD_DIR = "downloads"
MAX_CONCURRENT_DOWNLOADS = 5
