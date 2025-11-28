import os
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

TOKEN = os.getenv("BOT_TOKEN")
Q_ADMIN = int(os.getenv("Q_ADMIN"))
TARGET_CHAT = int(os.getenv("TARGET_CHAT"))
TARGET_TOPIC = int(os.getenv("TARGET_TOPIC"))
ADMINS = set(map(int, os.getenv("ADMINS").split(",")))

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

pending_messages = {}

# ---------- ПОЛУЧЕНИЕ СООБЩЕНИЯ ----------
@dp.message_handler()
async def receive_message(msg: types.Message):
    pending_messages[msg.message_id] = msg

    # Для Q_ADMIN
    info = f"📩 Новое сообщение\n👤 От: @{msg.from_user.username or 'нет username'}\n🆔 ID: {msg.from_user.id}\n📎 Message ID: {msg.message_id}"
    await bot.send_message(Q_ADMIN, info)
    await msg.forward(Q_ADMIN)

    # Для админов (анонимно)
    for admin_id in ADMINS:
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton("Отправить ✅", callback_data=f"send:{msg.message_id}"),
            types.InlineKeyboardButton("Не отправлять ❌", callback_data=f"deny:{msg.message_id}")
        )
        await msg.forward(admin_id)
        await bot.send_message(admin_id, f"Сообщение #{msg.message_id}\nЧто делаем?", reply_markup=kb)

# ---------- Callback: ОТПРАВИТЬ ----------
@dp.callback_query_handler(lambda c: c.data.startswith("send"))
async def send_message(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return await callback.answer("Это доступно только администраторам.", show_alert=True)

    msg_id = int(callback.data.split(":")[1])
    original = pending_messages.get(msg_id)
    if not original:
        return await callback.answer("Сообщение уже обработано.")

    # Отправляем в тему
    if original.photo:
        await bot.send_photo(TARGET_CHAT, original.photo[-1].file_id, caption=original.caption or "", message_thread_id=TARGET_TOPIC)
    elif original.video:
        await bot.send_video(TARGET_CHAT, original.video.file_id, caption=original.caption or "", message_thread_id=TARGET_TOPIC)
    elif original.document:
        await bot.send_document(TARGET_CHAT, original.document.file_id, caption=original.caption or "", message_thread_id=TARGET_TOPIC)
    else:
        await bot.send_message(TARGET_CHAT, original.text or "", message_thread_id=TARGET_TOPIC)

    await bot.send_message(Q_ADMIN, f"✅ Сообщение #{msg_id} — ОТПРАВЛЕНО")
    del pending_messages[msg_id]
    await callback.answer("Отправлено!")
    await callback.message.edit_reply_markup()

# ---------- Callback: НЕ ОТПРАВЛЯТЬ ----------
@dp.callback_query_handler(lambda c: c.data.startswith("deny"))
async def deny_message(callback: types.CallbackQuery):
    msg_id = int(callback.data.split(":")[1])
    if msg_id in pending_messages:
        del pending_messages[msg_id]

    await bot.send_message(Q_ADMIN, f"❌ Сообщение #{msg_id} — ОТКЛОНЕНО")
    await callback.answer("Отклонено", show_alert=True)
    await callback.message.edit_reply_markup()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
