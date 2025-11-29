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
    pending_messages[msg.message_id] = msg
    admin_messages[msg.message_id] = []

    info = (
        f"📩 Новое сообщение\n"
        f"👤 От: @{msg.from_user.username or 'нет username'}\n"
        f"🆔 ID: {msg.from_user.id}\n"
        f"📎 Message ID: {msg.message_id}"
    )
    await bot.send_message(Q_ADMIN, info)
    await msg.forward(Q_ADMIN)

    for admin_id in ADMINS:
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton("Отправить ✅", callback_data=f"send:{msg.message_id}"),
            types.InlineKeyboardButton("Не отправлять ❌", callback_data=f"deny:{msg.message_id}")
        )

        await bot.copy_message(admin_id, msg.chat.id, msg.message_id)
        admin_msg = await bot.send_message(admin_id, f"Сообщение #{msg.message_id}\nЧто делаем?", reply_markup=kb)

        admin_messages[msg.message_id].append((admin_id, admin_msg.message_id))


async def remove_keyboards(msg_id: int):
    if msg_id not in admin_messages:
        return

    for admin_id, admin_msg_id in admin_messages[msg_id]:
        try:
            await bot.edit_message_reply_markup(admin_id, admin_msg_id, reply_markup=None)
        except:
            pass


@dp.callback_query_handler(lambda c: c.data.startswith("send"))
async def send_message(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS and callback.from_user.id != Q_ADMIN:
        return await callback.answer("Нет доступа", show_alert=True)

    msg_id = int(callback.data.split(":")[1])
    original = pending_messages.get(msg_id)

    if not original:
        await remove_keyboards(msg_id)
        return await callback.answer("Уже обработано", show_alert=True)

    await bot.copy_message(
        chat_id=TARGET_CHAT,
        from_chat_id=original.chat.id,
        message_id=original.message_id,
        message_thread_id=TARGET_TOPIC
    )

    await remove_keyboards(msg_id)
    await bot.send_message(Q_ADMIN, f"✅ Сообщение #{msg_id} — ОТПРАВЛЕНО")

    del pending_messages[msg_id]
    del admin_messages[msg_id]

    await callback.answer("Отправлено!")
    await callback.message.edit_reply_markup()


@dp.callback_query_handler(lambda c: c.data.startswith("deny"))
async def deny_message(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS and callback.from_user.id != Q_ADMIN:
        return await callback.answer("Нет доступа", show_alert=True)

    msg_id = int(callback.data.split(":")[1])

    await remove_keyboards(msg_id)

    if msg_id in pending_messages:
        del pending_messages[msg_id]
    if msg_id in admin_messages:
        del admin_messages[msg_id]

    await bot.send_message(Q_ADMIN, f"❌ Сообщение #{msg_id} — ОТКЛОНЕНО")

    await callback.answer("Отклонено")
    await callback.message.edit_reply_markup()


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
