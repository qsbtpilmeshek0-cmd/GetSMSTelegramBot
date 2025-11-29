# DarknetBot.py
import os
import json
import uuid
import time
import asyncio
from typing import Dict, List, Tuple
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------- Конфигурация из окружения ----------
TOKEN = os.getenv("BOT_TOKEN")
Q_ADMIN = int(os.getenv("Q_ADMIN"))
TARGET_CHAT = int(os.getenv("TARGET_CHAT"))
# Если не используешь темы, можно оставить пустым или None в env — тогда не передаём message_thread_id
TARGET_TOPIC = os.getenv("TARGET_TOPIC")
if TARGET_TOPIC is not None and TARGET_TOPIC != "":
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

# ---------- Инициализация бота ----------
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ---------- Внутренние структуры ----------
# request_id -> { "chat_id": int, "msg_id": int, "from_user_id": int, "from_username": str, "ts": float }
pending: Dict[str, Dict] = {}
# request_id -> list of (admin_id, buttons_message_id)
admin_msgs: Dict[str, List[Tuple[int, int]]] = {}
# processed request ids (чтобы защититься от повторной обработки)
processed: Dict[str, str] = {}

# ---------- Файлы для персистентности ----------
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
        # convert keys to str and tuples properly
        admin_msgs = {k: [(int(x[0]), int(x[1])) for x in v] for k, v in a.items()}
    pr = safe_read(PROCESSED_FILE)
    if isinstance(pr, dict):
        processed = pr


load_all()

LOCK = asyncio.Lock()


def build_keyboard(rid: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("Отправить ✅", callback_data=f"send:{rid}"),
        InlineKeyboardButton("Отклонить ❌", callback_data=f"deny:{rid}")
    )
    return kb


async def send_admin_panel(admin_id: int, orig: types.Message, rid: str):
    """
    Отправляет администратору:
      1) копию сообщения (orig.copy_to)
      2) отдельное сообщение с кнопками (reply_markup)
    Возвращает tuple (copied_message_id, buttons_message_id) или (None, None) при ошибке.
    """
    try:
        copied = await orig.copy_to(admin_id)
    except Exception:
        # не можем доставить копию (возможно админ заблокировал бота) — пропускаем
        return None, None

    try:
        kb = build_keyboard(rid)
        buttons_msg = await bot.send_message(admin_id, "Что делаем с сообщением?", reply_markup=kb)
        return copied.message_id, buttons_msg.message_id
    except Exception:
        # удалим копию, если кнопки не отправились (попробуем быть аккуратными)
        # (не критично — просто не добавляем в admin_msgs)
        return None, None


async def clear_keyboards(rid: str):
    """
    Удаляет кнопки у всех админов для данного request.
    """
    entries = admin_msgs.get(rid, [])
    for admin_id, buttons_msg_id in list(entries):
        try:
            await bot.edit_message_reply_markup(admin_id, buttons_msg_id, reply_markup=None)
        except Exception:
            pass
    admin_msgs.pop(rid, None)
    persist_all()


@dp.message_handler(lambda m: m.chat.type == "private")
async def handle_private(msg: types.Message):
    """
    Принимаем только личные сообщения.
    Создаём уникальный request_id и рассылаем админам копию + панель.
    """
    # build unique request id
    rid = uuid.uuid4().hex  # 32 hex chars

    # store minimal original reference
    pending[rid] = {
        "chat_id": int(msg.chat.id),
        "msg_id": int(msg.message_id),
        "from_user_id": int(msg.from_user.id),
        "from_username": msg.from_user.username or "",
        "ts": time.time()
    }
    admin_msgs[rid] = []
    persist_all()

    # Silent log only to Q_ADMIN
    try:
        log_text = (
            f"📩 Новое сообщение\n"
            f"👤 @{pending[rid]['from_username'] or 'нет username'}\n"
            f"🆔 {pending[rid]['from_user_id']}\n"
            f"RID: {rid}"
        )
        await bot.send_message(Q_ADMIN, log_text)
        # copy original to Q_ADMIN (private)
        try:
            await msg.copy_to(Q_ADMIN)
        except Exception:
            pass
    except Exception:
        pass

    # send to admins (including Q_ADMIN to hide role)
    targets = set(ADMINS)
    targets.add(Q_ADMIN)

    async with LOCK:
        for admin_id in list(targets):
            copied_id, buttons_id = await send_admin_panel(admin_id, msg, rid)
            if copied_id is not None and buttons_id is not None:
                admin_msgs[rid].append((admin_id, buttons_id))
        persist_all()


@dp.callback_query_handler(lambda c: c.data and (c.data.startswith("send:") or c.data.startswith("deny:")))
async def handle_moderation(cb: types.CallbackQuery):
    """
    Обработка нажатий. Только ADMINS и Q_ADMIN имеют право.
    Silent ignore для остальных.
    """
    uid = cb.from_user.id
    if uid not in ADMINS and uid != Q_ADMIN:
        # тихо игнорируем
        try:
            await cb.answer(cache_time=0)
        except Exception:
            pass
        return

    try:
        action, rid = cb.data.split(":", 1)
    except Exception:
        await cb.answer()
        return

    # avoid race: acquire lock
    async with LOCK:
        if rid in processed:
            # уже обработано
            try:
                await cb.answer("Уже обработано")
            except Exception:
                pass
            # remove buttons on this particular admin message too (best effort)
            try:
                await cb.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

        info = pending.get(rid)
        if not info:
            try:
                await cb.answer("Устарело")
            except Exception:
                pass
            # clean buttons for this admin
            try:
                await cb.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

        # mark processed immediately to avoid duplicates
        processed[rid] = f"{action}:{uid}:{int(time.time())}"
        persist_all()

        # if approved, copy original into target chat/topic
        if action == "send":
            try:
                if TARGET_TOPIC:
                    await bot.copy_message(
                        TARGET_CHAT,
                        info["chat_id"],
                        info["msg_id"],
                        message_thread_id=TARGET_TOPIC
                    )
                else:
                    await bot.copy_message(
                        TARGET_CHAT,
                        info["chat_id"],
                        info["msg_id"]
                    )
            except Exception:
                # не фатально — просто продолжим
                pass

        # remove keyboards for everyone
        await clear_keyboards(rid)

        # log only to Q_ADMIN (silent for others)
        try:
            if uid == Q_ADMIN:
                # If Q_ADMIN himself acted, notify him privately (keeps stealth)
                await bot.send_message(Q_ADMIN, f"📌 RID {rid} — выполнено: {action.upper()}")
            else:
                # Notify Q_ADMIN who acted (stealthy): only info about action, not revealing role
                await bot.send_message(Q_ADMIN,
                    f"📌 RID {rid} — {action.upper()} by {uid}"
                )
        except Exception:
            pass

        # cleanup
        pending.pop(rid, None)
        admin_msgs.pop(rid, None)
        persist_all()

        try:
            await cb.answer("Готово")
        except Exception:
            pass

        # remove buttons on the admin's own panel
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


if __name__ == "__main__":
    # graceful shutdown: persist on exit
    try:
        executor.start_polling(dp, skip_updates=True)
    finally:
        persist_all()
    
