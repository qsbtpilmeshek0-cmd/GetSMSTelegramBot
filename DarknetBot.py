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

pending = {}
admin_msgs = {}


def build_keyboard(msg_id: int):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("Отправить ✅", callback_data=f"send:{msg_id}"),
        types.InlineKeyboardButton("Отклонить ❌", callback_data=f"deny:{msg_id}")
    )
    return kb


async def send_to_admin(admin_id: int, msg: types.Message):
    kb = build_keyboard(msg.message_id)

    if msg.text:
        sent = await bot.send_message(admin_id, msg.text, reply_markup=kb)

    elif msg.photo:
        sent = await bot.send_photo(admin_id, msg.photo[-1].file_id,
                                    caption=msg.caption or "", reply_markup=kb)

    elif msg.video:
        sent = await bot.send_video(admin_id, msg.video.file_id,
                                    caption=msg.caption or "", reply_markup=kb)

    elif msg.document:
        sent = await bot.send_document(admin_id, msg.document.file_id,
                                       caption=msg.caption or "", reply_markup=kb)

    elif msg.voice:
        sent = await bot.send_voice(admin_id, msg.voice.file_id,
                                    caption=msg.caption or "", reply_markup=kb)

    elif msg.audio:
        sent = await bot.send_audio(admin_id, msg.audio.file_id,
                                    caption=msg.caption or "", reply_markup=kb)

    elif msg.sticker:
        await bot.send_sticker(admin_id, msg.sticker.file_id)
        sent = await bot.send_message(admin_id, "Что делаем с сообщением?", reply_markup=kb)

    else:
        sent = await bot.send_message(admin_id, "⚠️ Тип сообщения не поддерживается.",
                                      reply_markup=kb)

    return sent


# ⛔ Теперь бот принимает ТОЛЬКО личные сообщения
@dp.message_handler(lambda m: m.chat.type == "private")
async def receive_message(msg: types.Message):

    pending[msg.message_id] = msg
    admin_msgs[msg.message_id] = []

    # скрытое уведомление Q_ADMIN
    await bot.send_message(
        Q_ADMIN,
        f"📩 Новое сообщение от @{msg.from_user.username or 'user'} (ID {msg.from_user.id})"
    )

    # копия оригинала Q_ADMIN
    await msg.copy_to(Q_ADMIN)

    # все админы получают одно сообщение
    targets = ADMINS | {Q_ADMIN}
    for admin_id in targets:
        sent = await send_to_admin(admin_id, msg)
        admin_msgs[msg.message_id].append((admin_id, sent.message_id))


async def clear_keyboards(mid: int):
    if mid not in admin_msgs:
        return
    for admin_id, m_id in admin_msgs[mid]:
        try:
            await bot.edit_message_reply_markup(admin_id, m_id, None)
        except:
            pass


@dp.callback_query_handler(lambda c: c.data.startswith(("send", "deny")))
async def on_action(cb: types.CallbackQuery):
    uid = cb.from_user.id

    if uid not in ADMINS and uid != Q_ADMIN:
        return await cb.answer()

    action, msg_id = cb.data.split(":")
    msg_id = int(msg_id)

    orig = pending.get(msg_id)
    if not orig:
        return await cb.answer("Устарело", show_alert=False)

    if action == "send":
        await orig.copy_to(
            TARGET_CHAT,
            message_thread_id=TARGET_TOPIC
        )

    await clear_keyboards(msg_id)

    if uid == Q_ADMIN:
        await bot.send_message(Q_ADMIN, f"Готово: {action.upper()}")

    pending.pop(msg_id, None)
    admin_msgs.pop(msg_id, None)

    await cb.answer("Готово")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
