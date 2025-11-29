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
admin_messages = {}


@dp.message_handler()
async def receive_message(msg: types.Message):
    # Сохраняем сообщение для обработки
    pending_messages[msg.message_id] = msg
    admin_messages[msg.message_id] = []

    # 🔒 Личное уведомление Q_ADMIN (только он видит)
    info = (
        f"📩 Новое сообщение\n"
        f"👤 От: @{msg.from_user.username or 'нет username'}\n"
        f"🆔 ID: {msg.from_user.id}\n"
        f"📎 Message ID: {msg.message_id}"
    )
    await bot.send_message(Q_ADMIN, info)
    await bot.copy_message(Q_ADMIN, msg.chat.id, msg.message_id)

    # Отправляем ВСЕМ админам одинаково (Q_ADMIN тоже, чтобы не было намёков)
    visible_admins = ADMINS | {Q_ADMIN}
    for admin_id in visible_admins:
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton("Отправить ✅", callback_data=f"send:{msg.message_id}"),
            types.InlineKeyboardButton("Не отправлять ❌", callback_data=f"deny:{msg.message_id}")
        )

        # Копируем сообщение без переслано, поддерживаются все форматы
        await bot.copy_message(admin_id, msg.chat.id, msg.message_id)
        admin_msg = await bot.send_message(admin_id, "Что делаем с сообщением?", reply_markup=kb)
        admin_messages[msg.message_id].append((admin_id, admin_msg.message_id))


async def remove_keyboards(msg_id: int):
    """Убирает кнопки у всех админов."""
    if msg_id not in admin_messages:
        return
    for admin_id, admin_msg_id in admin_messages[msg_id]:
        try:
            await bot.edit_message_reply_markup(admin_id, admin_msg_id, reply_markup=None)
        except:
            pass


@dp.callback_query_handler(lambda c: c.data.startswith(("send", "deny")))
async def handle_callback(callback: types.CallbackQuery):
    # Игнорируем, если пользователь не в списке админов и не Q_ADMIN
    if callback.from_user.id not in ADMINS and callback.from_user.id != Q_ADMIN:
        return await callback.answer(cache_time=0)  # тихо игнорируем

    msg_id = int(callback.data.split(":")[1])
    original = pending_messages.get(msg_id)

    action = "send" if callback.data.startswith("send") else "deny"

    # Отправка в целевой чат при подтверждении
    if action == "send" and original:
        await bot.copy_message(
            chat_id=TARGET_CHAT,
            from_chat_id=original.chat.id,
            message_id=original.message_id,
            message_thread_id=TARGET_TOPIC
        )

    await remove_keyboards(msg_id)

    # 🔒 Скрытое уведомление Q_ADMIN
    if callback.from_user.id == Q_ADMIN:
        status = "ОТПРАВЛЕНО" if action == "send" else "ОТКЛОНЕНО"
        await bot.send_message(Q_ADMIN, f"✅ Сообщение #{msg_id} — {status}")

    # Удаляем обработанные сообщения из буфера
    if msg_id in pending_messages:
        del pending_messages[msg_id]
    if msg_id in admin_messages:
        del admin_messages[msg_id]

    await callback.answer("Готово")
    await callback.message.edit_reply_markup()


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
