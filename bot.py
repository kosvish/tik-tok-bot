import asyncio
import logging
import os
import time
import datetime
import random
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from lexicon import LEXICON
from database import Database

# ─────────────────────────────────────────
#  НАСТРОЙКИ
# ─────────────────────────────────────────
ADMIN_IDS = {636775647, 5448257664}
CHANNEL_ID = "-1003890716920"
ITALY_TZ = pytz.timezone("Europe/Rome")

WEEKDAY_NAMES = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}
WEEKDAY_SHORT = {
    0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"
}
TYPE_LABELS = {
    "text": "✍️ Текст",
    "photo": "🖼 Фото",
    "video": "🎬 Видео",
    "photo_text": "🖼+✍️ Фото+текст",
    "video_text": "🎬+✍️ Видео+текст",
}

background_tasks = set()
db = Database('bot.db')
logging.basicConfig(level=logging.INFO)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=ITALY_TZ)


# ─────────────────────────────────────────
#  СОСТОЯНИЯ
# ─────────────────────────────────────────
class WithdrawState(StatesGroup):
    waiting_for_wallet = State()

class VideoState(StatesGroup):
    waiting_for_click = State()
    waiting_for_comment = State()

class AdminState(StatesGroup):
    waiting_for_broadcast_text = State()

class PushState(StatesGroup):
    waiting_for_title = State()
    waiting_for_type = State()
    waiting_for_weekday = State()
    waiting_for_media = State()
    waiting_for_text = State()
    waiting_for_time = State()

class PushEditState(StatesGroup):
    choosing_field = State()
    waiting_for_title = State()
    waiting_for_type = State()
    waiting_for_weekday = State()
    waiting_for_media = State()
    waiting_for_text = State()
    waiting_for_time = State()


# ─────────────────────────────────────────
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────
async def delete_message_after(message: types.Message, sleep_time: int):
    await asyncio.sleep(sleep_time)
    try:
        await message.delete()
    except Exception:
        pass


def weekday_keyboard(callback_prefix: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора дня недели."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Пн", callback_data=f"{callback_prefix}0"),
            InlineKeyboardButton(text="Вт", callback_data=f"{callback_prefix}1"),
            InlineKeyboardButton(text="Ср", callback_data=f"{callback_prefix}2"),
            InlineKeyboardButton(text="Чт", callback_data=f"{callback_prefix}3"),
        ],
        [
            InlineKeyboardButton(text="Пт", callback_data=f"{callback_prefix}4"),
            InlineKeyboardButton(text="Сб", callback_data=f"{callback_prefix}5"),
            InlineKeyboardButton(text="Вс", callback_data=f"{callback_prefix}6"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_pushes")]
    ])


def type_keyboard(cancel_cb: str = "admin_pushes") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Только текст",    callback_data="ptype_text")],
        [InlineKeyboardButton(text="🖼 Только фото",     callback_data="ptype_photo")],
        [InlineKeyboardButton(text="🎬 Только видео",    callback_data="ptype_video")],
        [InlineKeyboardButton(text="🖼+✍️ Фото + текст", callback_data="ptype_photo_text")],
        [InlineKeyboardButton(text="🎬+✍️ Видео + текст",callback_data="ptype_video_text")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_cb)]
    ])


# ─────────────────────────────────────────
#  ПЛАНИРОВЩИК ПУШЕЙ
# ─────────────────────────────────────────
async def send_scheduled_push():
    now_italy = datetime.datetime.now(ITALY_TZ)
    current_time = now_italy.strftime("%H:%M")
    current_weekday = now_italy.weekday()   # 0=Пн … 6=Вс

    pushes = await db.get_active_pushes_for_schedule(current_weekday, current_time)
    if not pushes:
        return

    users = await db.get_all_users()
    for push in pushes:
        push_id, title, content_type, text, file_id = push
        sent = 0
        errors = 0
        for user_id in users:
            try:
                await _send_push_to_user(user_id, content_type, text, file_id)
                sent += 1
                await asyncio.sleep(0.05)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                try:
                    await _send_push_to_user(user_id, content_type, text, file_id)
                    sent += 1
                except Exception:
                    errors += 1
            except Exception:
                errors += 1

        # Отключаем пуш — он одноразовый
        await db.deactivate_push(push_id)

        try:
            await bot.send_message(
                636775647,
                f"📬 <b>Пуш отправлен и остановлен!</b>\n\n"
                f"📌 Название: <b>{title}</b>\n"
                f"✅ Доставлено: {sent}\n"
                f"❌ Ошибок: {errors}",
                parse_mode="HTML"
            )
        except Exception:
            pass


async def _send_push_to_user(user_id: int, content_type: str, text: str, file_id: str):
    if content_type == "text":
        await bot.send_message(user_id, text, parse_mode="HTML")
    elif content_type == "photo":
        await bot.send_photo(user_id, photo=file_id)
    elif content_type == "photo_text":
        await bot.send_photo(user_id, photo=file_id, caption=text, parse_mode="HTML")
    elif content_type == "video":
        await bot.send_video(user_id, video=file_id)
    elif content_type == "video_text":
        await bot.send_video(user_id, video=file_id, caption=text, parse_mode="HTML")


# ─────────────────────────────────────────
#  ПОЛУЧЕНИЕ file_id (инструмент админа)
# ─────────────────────────────────────────
@dp.message(F.video)
async def handle_video(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state in (PushState.waiting_for_media, PushEditState.waiting_for_media):
        file_id = message.video.file_id
        await state.update_data(file_id=file_id)
        data = await state.get_data()
        content_type = data.get("content_type", "video")
        if content_type == "video":
            await state.set_state(
                PushState.waiting_for_time
                if current_state == PushState.waiting_for_media
                else PushEditState.waiting_for_time
            )
            await message.answer(
                "✅ Видео принято!\n\n"
                "🕐 <b>Введите время отправки</b> по итальянскому времени <code>ЧЧ:ММ</code>:",
                parse_mode="HTML"
            )
        else:
            await state.set_state(
                PushState.waiting_for_text
                if current_state == PushState.waiting_for_media
                else PushEditState.waiting_for_text
            )
            await message.answer("✅ Видео принято!\n\n✍️ Теперь введите <b>текст</b> подписи:", parse_mode="HTML")
        return
    if message.from_user.id not in ADMIN_IDS:
        await message.reply(f"✅ <b>File ID видео:</b>\n\n<code>{message.video.file_id}</code>", parse_mode="HTML")


@dp.message(F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state in (PushState.waiting_for_media, PushEditState.waiting_for_media):
        file_id = message.photo[-1].file_id
        await state.update_data(file_id=file_id)
        data = await state.get_data()
        content_type = data.get("content_type", "photo")
        if content_type == "photo":
            await state.set_state(
                PushState.waiting_for_time
                if current_state == PushState.waiting_for_media
                else PushEditState.waiting_for_time
            )
            await message.answer(
                "✅ Фото принято!\n\n"
                "🕐 <b>Введите время отправки</b> по итальянскому времени <code>ЧЧ:ММ</code>:",
                parse_mode="HTML"
            )
        else:
            await state.set_state(
                PushState.waiting_for_text
                if current_state == PushState.waiting_for_media
                else PushEditState.waiting_for_text
            )
            await message.answer("✅ Фото принято!\n\n✍️ Теперь введите <b>текст</b> подписи:", parse_mode="HTML")
        return
    if message.from_user.id not in ADMIN_IDS:
        await message.reply(f"✅ <b>File ID фото:</b>\n\n<code>{message.photo[-1].file_id}</code>", parse_mode="HTML")


# ─────────────────────────────────────────
#  ЛОГИКА ОТПРАВКИ ВИДЕО-ЗАДАНИЙ
# ─────────────────────────────────────────
async def send_video_task(message: types.Message, current_video: int, balance: float,
                          state: FSMContext, edit: bool = True):
    user_data = await state.get_data()
    tasks_queue = user_data.get('tasks_queue')
    if not tasks_queue:
        tasks_queue = ['like'] * 10 + ['comment'] * 5
        random.shuffle(tasks_queue)
        if tasks_queue[0] == 'comment':
            idx = tasks_queue.index('like')
            tasks_queue[0], tasks_queue[idx] = tasks_queue[idx], tasks_queue[0]
        await state.update_data(tasks_queue=tasks_queue)

    task_type = tasks_queue[current_video - 1]

    if task_type == 'like':
        reward = random.choice([0.70, 0.90, 1.20])
        duration = 0 if message.chat.id in ADMIN_IDS else 10
        caption = LEXICON['video_task'].format(
            current=current_video, reward=f"{reward:.2f}",
            task_text=LEXICON['task_like_dislike']['text'], balance=f"{balance:.2f}"
        )
        inline_kb = [
            [
                InlineKeyboardButton(text=f"👍 (+{reward:.2f}€)", callback_data="task_done",style="success"),
                InlineKeyboardButton(text=f"👎 (+{reward:.2f}€)", callback_data="task_done", style="danger"),
            ],
            [InlineKeyboardButton(text=LEXICON['btn_finish'], callback_data="main_menu")]
        ]
        await state.set_state(VideoState.waiting_for_click)
    else:
        reward = random.choice([2.50, 3.00, 3.50])
        duration = 0 if message.chat.id in ADMIN_IDS else 10
        caption = LEXICON['video_task'].format(
            current=current_video, reward=f"{reward:.2f}",
            task_text=LEXICON['task_comment']['text'], balance=f"{balance:.2f}"
        )
        inline_kb = [[InlineKeyboardButton(text=LEXICON['btn_finish'], callback_data="main_menu")]]
        await state.set_state(VideoState.waiting_for_comment)

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_kb)
    await state.update_data(unlock_time=time.time() + duration, current_reward=reward)
    video_id = LEXICON['videos'][current_video - 1]

    if edit:
        try:
            await message.edit_media(
                media=InputMediaVideo(media=video_id, caption=caption, parse_mode="HTML"),
                reply_markup=keyboard
            )
        except Exception:
            try:
                await message.delete()
            except Exception:
                pass
            await message.answer_video(video=video_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer_video(video=video_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")


# ─────────────────────────────────────────
#  СТАРТ И ГЛАВНОЕ МЕНЮ
# ─────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "amico"
    if not await db.user_exists(user_id):
        await db.add_user(user_id, user_name)
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=LEXICON['btn_informed'], callback_data="start_earning")]
        ])
        await message.answer(LEXICON['welcome_msg'].format(name=user_name), reply_markup=keyboard, parse_mode="HTML")
    else:
        balance, current_video = await db.get_user(user_id)
        if current_video <= 15:
            await message.answer("Bentornato! 📈 Continuiamo da dove avevi interrotto.")
            await state.update_data(balance=balance, current_video=current_video)
            await send_video_task(message, current_video, balance, state, edit=False)
        else:
            await state.update_data(balance=balance, current_video=current_video)
            await show_main_menu(message, edit=False)


async def show_main_menu(message: types.Message, edit: bool = True):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON['btn_earn'],     callback_data="earn")],
        [InlineKeyboardButton(text=LEXICON['btn_profile'],  callback_data="profile")],
        [InlineKeyboardButton(text=LEXICON['btn_withdraw'], callback_data="withdraw")],
        [InlineKeyboardButton(text=LEXICON['btn_partners'], callback_data="partners")]
    ])
    if edit:
        try:
            await message.edit_text(LEXICON['main_menu_text'], reply_markup=keyboard)
        except Exception:
            try:
                await message.delete()
            except Exception:
                pass
            await message.answer(LEXICON['main_menu_text'], reply_markup=keyboard)
    else:
        await message.answer(LEXICON['main_menu_text'], reply_markup=keyboard)


@dp.callback_query(F.data == "main_menu")
async def show_main_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main_menu(callback.message, edit=True)
    await callback.answer()


@dp.callback_query(F.data == "start_earning")
async def process_start_earning(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(balance=0.0, current_video=1)
    await send_video_task(callback.message, 1, 0.0, state, edit=True)


@dp.callback_query(F.data == "earn")
async def process_earn_button(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_data = await db.get_user(user_id)
    if not user_data:
        balance, current_video = 0.0, 1
    else:
        balance, current_video = user_data
        current_video = int(current_video)

    if current_video <= 15:
        await callback.answer("Caricamento video...")
        await state.update_data(balance=balance, current_video=current_video)
        try:
            await callback.message.delete()
        except Exception:
            pass
        await send_video_task(callback.message, current_video, balance, state, edit=False)
    else:
        await callback.answer("Limite raggiunto!", show_alert=True)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=LEXICON['btn_profile'], callback_data="profile")],
            [InlineKeyboardButton(text=LEXICON['btn_back'],    callback_data="main_menu")]
        ])
        try:
            await callback.message.edit_text(LEXICON['limit_reached'], reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await callback.message.answer(LEXICON['limit_reached'], reply_markup=keyboard, parse_mode="HTML")


# ─────────────────────────────────────────
#  ОБРАБОТКА ЗАДАНИЙ
# ─────────────────────────────────────────
@dp.callback_query(VideoState.waiting_for_click, F.data == "task_done")
async def process_task_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if time.time() < data.get("unlock_time", 0):
        await callback.answer(LEXICON['alert_too_fast'], show_alert=True)
        return
    user_id = callback.from_user.id
    user_data = await db.get_user(user_id)
    balance = float(user_data[0]) if user_data else 0.0
    current_reward = data.get("current_reward", 1.0)
    user_data = await db.get_user(callback.from_user.id)
    current_video = int(user_data[1]) if user_data else 1
    new_balance = round(balance + current_reward, 2)
    new_video = current_video + 1
    await callback.answer(f"✅ +{current_reward:.2f}€!")
    if new_video > 15:
        total_balance = round(new_balance + 20.0, 2)
        await db.update_user(callback.from_user.id, total_balance, new_video)
        await state.update_data(balance=total_balance)
        await state.set_state(None)
        try:
            await callback.message.delete()
        except Exception:
            pass
        try:
            text = LEXICON['finish_task'].format(balance=new_balance, total=total_balance)
        except Exception:
            text = f"🎉 Completato! {new_balance}€ + 20€ bonus = {total_balance}€"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=LEXICON.get('btn_menu', 'Menu'), callback_data="main_menu")]
        ])
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await db.update_user(callback.from_user.id, new_balance, new_video)
        await state.update_data(balance=new_balance, current_video=new_video)
        await send_video_task(callback.message, new_video, new_balance, state)


@dp.message(VideoState.waiting_for_comment)
async def process_comment_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    current_time = time.time()
    unlock_time = data.get("unlock_time", 0)
    if current_time < unlock_time:
        remaining = int(unlock_time - current_time)
        try:
            await message.delete()
        except Exception:
            pass
        warn = await message.answer(f"⏳ Aspetta ancora {remaining} sec.")
        task = asyncio.create_task(delete_message_after(warn, 3))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        return
    if len(message.text or "") < 15:
        try:
            await message.delete()
        except Exception:
            pass
        warn = await message.answer("⚠️ Commento troppo corto! Minimo 15 caratteri.")
        asyncio.create_task(delete_message_after(warn, 3))
        return
    balance = data.get("balance", 0.0)
    current_reward = data.get("current_reward", 1.0)
    user_data = await db.get_user(message.from_user.id)
    current_video = int(user_data[1]) if user_data else 1
    new_balance = round(balance + current_reward, 2)
    new_video = current_video + 1
    try:
        await message.delete()
    except Exception:
        pass
    if new_video > 15:
        total_balance = round(new_balance + 20.0, 2)
        await db.update_user(message.from_user.id, total_balance, new_video)
        await state.update_data(balance=total_balance)
        await state.set_state(None)
        try:
            text = LEXICON['finish_task'].format(balance=new_balance, total=total_balance)
        except Exception:
            text = f"🎉 Completato! {new_balance}€ + 20€ bonus = {total_balance}€"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=LEXICON.get('btn_menu', 'Menu'), callback_data="main_menu")]
        ])
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await db.update_user(message.from_user.id, new_balance, new_video)
        await state.update_data(balance=new_balance, current_video=new_video)
        await send_video_task(message, new_video, new_balance, state, edit=False)


# ─────────────────────────────────────────
#  ЧИТ-КОДЫ
# ─────────────────────────────────────────
@dp.message(Command("reset"))
async def cmd_reset(message: types.Message, state: FSMContext):
    await db.update_user(message.from_user.id, 0.0, 1)
    await state.clear()
    await message.answer("🔄 <b>Прогресс сброшен!</b> Нажми /start", parse_mode="HTML")


@dp.message(Command("jump"))
async def cmd_jump(message: types.Message, state: FSMContext):
    await db.update_user(message.from_user.id, 45.0, 10)
    await state.update_data(balance=45.0, current_video=10)
    await message.answer("🦘 <b>Прыжок!</b> Ты на 10-м видео.", parse_mode="HTML")


# ─────────────────────────────────────────
#  ПРОФИЛЬ / ВЫВОД / ПАРТНЁРЫ
# ─────────────────────────────────────────
@dp.callback_query(F.data == "profile")
async def process_profile(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_data = await db.get_user(user_id)
    balance, current_video = user_data if user_data else (0.0, 1)
    text = LEXICON['profile_text'].format(
        name=callback.from_user.first_name,
        username=callback.from_user.username or "Senza_username",
        balance=f"{balance:.2f}",
        video_count=min(current_video - 1, 15)
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON['btn_earn'], callback_data="earn")],
        [InlineKeyboardButton(text="🎁 Ricevi 10.000 €", url="https://t.me/+06DdEkcYVHtmYTIy")],
        [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="main_menu")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "withdraw")
async def process_withdraw(callback: types.CallbackQuery, state: FSMContext):
    user_data = await db.get_user(callback.from_user.id)
    balance = user_data[0] if user_data else (await state.get_data()).get("balance", 0)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=LEXICON['btn_phone'],   callback_data="pay_phone"),
            InlineKeyboardButton(text=LEXICON['btn_paypal'],  callback_data="pay_paypal")
        ],
        [
            InlineKeyboardButton(text=LEXICON['btn_binance'], callback_data="pay_binance"),
            InlineKeyboardButton(text=LEXICON['btn_card'],    callback_data="pay_card")
        ],
        [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="main_menu")]
    ])
    await callback.message.edit_text(
        LEXICON['withdraw_text'].format(balance=f"{balance:.2f}"),
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("pay_"))
async def ask_for_details(callback: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="withdraw")]
    ])
    await callback.message.edit_text(LEXICON['ask_wallet_generic'], reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()
    await state.set_state(WithdrawState.waiting_for_wallet)


@dp.message(WithdrawState.waiting_for_wallet)
async def process_wallet_details(message: types.Message, state: FSMContext):
    if len(message.text) < 8:
        await message.answer(LEXICON['invalid_details'], parse_mode="HTML")
        return
    msg = await message.answer(LEXICON['processing_1'], parse_mode="HTML")
    await asyncio.sleep(2)
    await msg.edit_text(LEXICON['processing_2'], parse_mode="HTML")
    await asyncio.sleep(2)
    balance = (await state.get_data()).get("balance", 0)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON['btn_check_sub_now'], callback_data="verify_subscription")],
        [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="main_menu")]
    ])
    await msg.edit_text(
        LEXICON['withdraw_trap'].format(balance=f"{balance:.2f}", details=message.text),
        reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True
    )
    await state.set_state(None)


@dp.callback_query(F.data == "verify_subscription")
async def check_user_subscription(callback: types.CallbackQuery):
    try:
        member = await callback.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=callback.from_user.id)
        if member.status in ['left', 'kicked']:
            await callback.answer("❌ Non sei ancora iscritto!", show_alert=True)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=LEXICON['btn_subscribe'], url="https://t.me/+Fdt1AaN0Pu9iNGNi")],
                [InlineKeyboardButton(text=LEXICON['btn_check_sub_now'], callback_data="verify_subscription")]
            ])
            await callback.message.edit_text(LEXICON['sub_required_text'], reply_markup=keyboard, parse_mode="HTML")
        else:
            await callback.answer("✅ Verifica completata!")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📱 Contatta il Manager", url="https://t.me/monica_guadagno")],
                [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="main_menu")]
            ])
            await callback.message.edit_text(LEXICON['sub_success'], reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка подписки: {e}")
        await callback.answer("⚠️ Errore tecnico.", show_alert=True)


@dp.callback_query(F.data == "partners")
async def process_partners_menu(callback: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON['btn_partner_channel'], url="https://t.me/+Fdt1AaN0Pu9iNGNi")],
        [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="main_menu")]
    ])
    try:
        await callback.message.edit_text(LEXICON['partners_text'], reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(LEXICON['partners_text'], reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ═══════════════════════════════════════════════════════════
#  А Д М И Н - П А Н Е Л Ь
# ═══════════════════════════════════════════════════════════

def _admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика",      callback_data="admin_stats")],
        [InlineKeyboardButton(text="📬 Пуш-рассылки",   callback_data="admin_pushes")],
        [InlineKeyboardButton(text="📢 Быстрая рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="❌ Выход",           callback_data="main_menu")]
    ])


@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
            "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
            reply_markup=_admin_keyboard(), parse_mode="HTML"
        )


@dp.callback_query(F.data == "admin_panel")
async def back_to_admin(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    try:
        await callback.message.edit_text(
            "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
            reply_markup=_admin_keyboard(), parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
            reply_markup=_admin_keyboard(), parse_mode="HTML"
        )
    await callback.answer()


# ───── СТАТИСТИКА ─────
@dp.callback_query(F.data == "admin_stats")
async def show_stats(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    total_users, total_money = await db.get_stats()
    pushes = await db.get_all_pushes()
    active_pushes = sum(1 for p in pushes if p[5] == 1)
    now_italy = datetime.datetime.now(ITALY_TZ).strftime("%H:%M:%S")
    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего участников: <b>{total_users}</b>\n"
        f"💰 Начислено всего: <b>{total_money:.2f} €</b>\n"
        f"📬 Активных пушей: <b>{active_pushes}</b> / {len(pushes)}\n\n"
        f"🕒 Время (Италия): <i>{now_italy}</i>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔙 Назад",    callback_data="admin_panel")]
    ])
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except TelegramBadRequest:
        await callback.answer("Уже актуально ✅")


# ───── БЫСТРАЯ РАССЫЛКА ─────
@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.message.answer(
        "📢 <b>Быстрая рассылка</b>\n\n"
        "Отправьте сообщение — оно уйдёт всем пользователям <b>немедленно</b>.",
        parse_mode="HTML"
    )
    await state.set_state(AdminState.waiting_for_broadcast_text)
    await callback.answer()


@dp.message(AdminState.waiting_for_broadcast_text)
async def perform_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    users = await db.get_all_users()
    count = 0
    errors = 0
    status_msg = await message.answer(f"🚀 Начинаю рассылку на {len(users)} чел...")
    for user_id in users:
        try:
            await message.send_copy(chat_id=user_id)
            count += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await message.send_copy(chat_id=user_id)
                count += 1
            except Exception:
                errors += 1
        except Exception:
            errors += 1
    await status_msg.edit_text(
        f"✅ <b>Готово!</b>\n\n📈 Доставлено: {count}\n📉 Ошибок: {errors}",
        parse_mode="HTML"
    )
    await state.clear()


# ═══════════════════════════════════════════════════════════
#  П У Ш - Р А С С Ы Л К И
# ═══════════════════════════════════════════════════════════

@dp.callback_query(F.data == "admin_pushes")
async def admin_pushes_menu(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить пуш",  callback_data="push_add")],
        [InlineKeyboardButton(text="📋 Список пушей",  callback_data="push_list")],
        [InlineKeyboardButton(text="✏️ Изменить пуш",  callback_data="push_edit_list")],
        [InlineKeyboardButton(text="🗑 Удалить пуш",   callback_data="push_delete_list")],
        [InlineKeyboardButton(text="🔙 Назад",         callback_data="admin_panel")]
    ])
    try:
        await callback.message.edit_text(
            "📬 <b>Пуш-рассылки</b>\n\n"
            "Пуш отправляется один раз в выбранный день и время по <b>итальянскому времени</b>, "
            "после чего автоматически останавливается.",
            reply_markup=keyboard, parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            "📬 <b>Пуш-рассылки</b>\n\n"
            "Пуш отправляется один раз в выбранный день и время по <b>итальянскому времени</b>, "
            "после чего автоматически останавливается.",
            reply_markup=keyboard, parse_mode="HTML"
        )
    await callback.answer()


# ══════════════════════════════
#  ДОБАВИТЬ ПУШ
# ══════════════════════════════

@dp.callback_query(F.data == "push_add")
async def push_add_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await state.set_state(PushState.waiting_for_title)
    await callback.message.edit_text(
        "➕ <b>Новый пуш — шаг 1 из 4</b>\n\n"
        "Введите <b>название</b> пуша (только для вас):\n"
        "<i>Например: Утренний пуш понедельник</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message(PushState.waiting_for_title)
async def push_got_title(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(PushState.waiting_for_type)
    await message.answer(
        "➕ <b>Новый пуш — шаг 2 из 4</b>\n\nВыберите <b>тип контента</b>:",
        reply_markup=type_keyboard(), parse_mode="HTML"
    )


@dp.callback_query(PushState.waiting_for_type, F.data.startswith("ptype_"))
async def push_got_type(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    content_type = callback.data.replace("ptype_", "")
    await state.update_data(content_type=content_type)
    await state.set_state(PushState.waiting_for_weekday)
    await callback.message.edit_text(
        "➕ <b>Новый пуш — шаг 3 из 4</b>\n\nВыберите <b>день недели</b> отправки:",
        reply_markup=weekday_keyboard("push_weekday_"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(PushState.waiting_for_weekday, F.data.startswith("push_weekday_"))
async def push_got_weekday(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    weekday = int(callback.data.replace("push_weekday_", ""))
    await state.update_data(send_weekday=weekday)
    data = await state.get_data()
    content_type = data.get("content_type")

    if content_type == "text":
        await state.set_state(PushState.waiting_for_text)
        await callback.message.edit_text(
            f"➕ <b>Новый пуш — шаг 4 из 4</b>\n\n"
            f"День: <b>{WEEKDAY_NAMES[weekday]}</b>\n\n"
            f"✍️ Введите <b>текст</b> пуша (поддерживается HTML):",
            parse_mode="HTML"
        )
    else:
        await state.set_state(PushState.waiting_for_media)
        media_word = "фото" if "photo" in content_type else "видео"
        await callback.message.edit_text(
            f"➕ <b>Новый пуш — шаг 4 из 4</b>\n\n"
            f"День: <b>{WEEKDAY_NAMES[weekday]}</b>\n\n"
            f"📎 Отправьте <b>{media_word}</b>:",
            parse_mode="HTML"
        )
    await callback.answer()


@dp.message(PushState.waiting_for_text)
async def push_got_text(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.update_data(text=message.text)
    data = await state.get_data()
    content_type = data.get("content_type")
    # Если это photo_text/video_text — медиа уже есть, идём к времени
    # Если это просто text — тоже идём к времени
    if content_type in ("text", "photo_text", "video_text") and data.get("file_id") is not None or content_type == "text":
        await state.set_state(PushState.waiting_for_time)
        await message.answer(
            "🕐 <b>Введите время отправки</b> по итальянскому времени в формате <code>ЧЧ:ММ</code>:\n"
            "<i>Например: 09:00</i>",
            parse_mode="HTML"
        )


@dp.message(PushState.waiting_for_time)
async def push_got_time(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    send_time = _parse_time(message.text.strip())
    if not send_time:
        await message.answer("❌ Неверный формат! Введите как <code>ЧЧ:ММ</code>, например <code>10:30</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    await db.add_push(
        title=data.get("title", "Без названия"),
        content_type=data.get("content_type", "text"),
        send_weekday=data.get("send_weekday", 0),
        send_time=send_time,
        text=data.get("text"),
        file_id=data.get("file_id")
    )
    await state.clear()

    weekday = data.get("send_weekday", 0)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📬 К пушам",  callback_data="admin_pushes")],
        [InlineKeyboardButton(text="🛠 В панель", callback_data="admin_panel")]
    ])
    await message.answer(
        f"✅ <b>Пуш создан!</b>\n\n"
        f"📌 Название: <b>{data.get('title')}</b>\n"
        f"📎 Тип: {TYPE_LABELS.get(data.get('content_type'), '?')}\n"
        f"📅 День: <b>{WEEKDAY_NAMES[weekday]}</b>\n"
        f"🕐 Время: <b>{send_time}</b> (Италия)\n\n"
        f"<i>После отправки пуш автоматически остановится.</i>",
        reply_markup=keyboard, parse_mode="HTML"
    )


# ══════════════════════════════
#  СПИСОК ПУШЕЙ
# ══════════════════════════════

@dp.callback_query(F.data == "push_list")
async def push_list(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    pushes = await db.get_all_pushes()
    if not pushes:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить", callback_data="push_add")],
            [InlineKeyboardButton(text="🔙 Назад",   callback_data="admin_pushes")]
        ])
        try:
            await callback.message.edit_text(
                "📋 <b>Список пушей</b>\n\n<i>Пушей пока нет.</i>",
                reply_markup=keyboard, parse_mode="HTML"
            )
        except Exception:
            pass
        await callback.answer()
        return

    lines = ["📋 <b>Все пуши:</b>\n"]
    buttons = []
    for push in pushes:
        pid, title, content_type, weekday, send_time, is_active = push
        status = "🟢" if is_active else "🔴"
        icon = {"text": "✍️", "photo": "🖼", "video": "🎬", "photo_text": "🖼✍️", "video_text": "🎬✍️"}.get(content_type, "📎")
        lines.append(f"{status} {icon} <b>{title}</b>\n    📅 {WEEKDAY_NAMES[weekday]}  🕐 {send_time}")
        lbl = "⏸" if is_active else "▶️"
        buttons.append([InlineKeyboardButton(
            text=f"{lbl} {title[:22]}",
            callback_data=f"push_toggle_{pid}"
        )])

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_pushes")])
    try:
        await callback.message.edit_text(
            "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer()


@dp.callback_query(F.data.startswith("push_toggle_"))
async def push_toggle(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    push_id = int(callback.data.replace("push_toggle_", ""))
    new_status = await db.toggle_push(push_id)
    status_text = "включён 🟢" if new_status == 1 else "остановлен 🔴"
    await callback.answer(f"Пуш #{push_id} {status_text}")
    await push_list(callback)


# ══════════════════════════════
#  РЕДАКТИРОВАТЬ ПУШ
# ══════════════════════════════

@dp.callback_query(F.data == "push_edit_list")
async def push_edit_list(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    pushes = await db.get_all_pushes()
    if not pushes:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_pushes")]
        ])
        try:
            await callback.message.edit_text(
                "✏️ <b>Редактирование</b>\n\n<i>Нечего редактировать.</i>",
                reply_markup=keyboard, parse_mode="HTML"
            )
        except Exception:
            pass
        await callback.answer()
        return

    buttons = []
    for push in pushes:
        pid, title, content_type, weekday, send_time, is_active = push
        status = "🟢" if is_active else "🔴"
        buttons.append([InlineKeyboardButton(
            text=f"{status} ✏️ {title[:25]} ({WEEKDAY_SHORT[weekday]} {send_time})",
            callback_data=f"push_edit_{pid}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_pushes")])
    try:
        await callback.message.edit_text(
            "✏️ <b>Выберите пуш для редактирования:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer()


@dp.callback_query(F.data.startswith("push_edit_") & ~F.data.startswith("push_edit_list"))
async def push_edit_show(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    push_id = int(callback.data.replace("push_edit_", ""))
    push = await db.get_push_by_id(push_id)
    if not push:
        await callback.answer("Пуш не найден", show_alert=True)
        return

    pid, title, content_type, text, file_id, weekday, send_time, is_active = push
    # Сохраняем текущие данные пуша в state для редактирования
    await state.update_data(
        edit_push_id=push_id,
        title=title, content_type=content_type,
        text=text, file_id=file_id,
        send_weekday=weekday, send_time=send_time
    )
    await state.set_state(PushEditState.choosing_field)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📌 Название",   callback_data="pedit_title")],
        [InlineKeyboardButton(text="📎 Тип контента", callback_data="pedit_type")],
        [InlineKeyboardButton(text="📅 День недели", callback_data="pedit_weekday")],
        [InlineKeyboardButton(text="🕐 Время",       callback_data="pedit_time")],
        [InlineKeyboardButton(text="✍️ Текст",       callback_data="pedit_text")],
        [InlineKeyboardButton(text="🖼 Медиафайл",   callback_data="pedit_media")],
        [InlineKeyboardButton(text="💾 Сохранить",   callback_data="pedit_save")],
        [InlineKeyboardButton(text="❌ Отмена",       callback_data="push_edit_list")]
    ])
    await callback.message.edit_text(
        f"✏️ <b>Редактирование пуша</b>\n\n"
        f"📌 Название: <b>{title}</b>\n"
        f"📎 Тип: {TYPE_LABELS.get(content_type, '?')}\n"
        f"📅 День: <b>{WEEKDAY_NAMES[weekday]}</b>\n"
        f"🕐 Время: <b>{send_time}</b>\n"
        f"✍️ Текст: {text[:40] + '...' if text and len(text) > 40 else (text or '—')}\n\n"
        f"Что изменить?",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(PushEditState.choosing_field, F.data == "pedit_title")
async def pedit_title(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PushEditState.waiting_for_title)
    await callback.message.edit_text("✏️ Введите <b>новое название</b> пуша:", parse_mode="HTML")
    await callback.answer()


@dp.message(PushEditState.waiting_for_title)
async def pedit_got_title(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(PushEditState.choosing_field)
    await message.answer("✅ Название обновлено. Не забудь нажать <b>«💾 Сохранить»</b>.", parse_mode="HTML")
    await _show_edit_menu(message, state)


@dp.callback_query(PushEditState.choosing_field, F.data == "pedit_type")
async def pedit_type(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PushEditState.waiting_for_type)
    await callback.message.edit_text(
        "✏️ Выберите <b>новый тип контента</b>:",
        reply_markup=type_keyboard("push_edit_list"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(PushEditState.waiting_for_type, F.data.startswith("ptype_"))
async def pedit_got_type(callback: types.CallbackQuery, state: FSMContext):
    content_type = callback.data.replace("ptype_", "")
    await state.update_data(content_type=content_type)
    await state.set_state(PushEditState.choosing_field)
    await callback.answer("✅ Тип обновлён")
    await _show_edit_menu_cb(callback, state)


@dp.callback_query(PushEditState.choosing_field, F.data == "pedit_weekday")
async def pedit_weekday(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PushEditState.waiting_for_weekday)
    await callback.message.edit_text(
        "✏️ Выберите <b>новый день недели</b>:",
        reply_markup=weekday_keyboard("pedit_weekday_"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(PushEditState.waiting_for_weekday, F.data.startswith("pedit_weekday_"))
async def pedit_got_weekday(callback: types.CallbackQuery, state: FSMContext):
    weekday = int(callback.data.replace("pedit_weekday_", ""))
    await state.update_data(send_weekday=weekday)
    await state.set_state(PushEditState.choosing_field)
    await callback.answer(f"✅ День: {WEEKDAY_NAMES[weekday]}")
    await _show_edit_menu_cb(callback, state)


@dp.callback_query(PushEditState.choosing_field, F.data == "pedit_time")
async def pedit_time(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PushEditState.waiting_for_time)
    await callback.message.edit_text(
        "✏️ Введите <b>новое время</b> в формате <code>ЧЧ:ММ</code> (Италия):", parse_mode="HTML"
    )
    await callback.answer()


@dp.message(PushEditState.waiting_for_time)
async def pedit_got_time(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    send_time = _parse_time(message.text.strip())
    if not send_time:
        await message.answer("❌ Неверный формат! Введите <code>ЧЧ:ММ</code>", parse_mode="HTML")
        return
    await state.update_data(send_time=send_time)
    await state.set_state(PushEditState.choosing_field)
    await message.answer("✅ Время обновлено.")
    await _show_edit_menu(message, state)


@dp.callback_query(PushEditState.choosing_field, F.data == "pedit_text")
async def pedit_text(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PushEditState.waiting_for_text)
    await callback.message.edit_text("✏️ Введите <b>новый текст</b> пуша:", parse_mode="HTML")
    await callback.answer()


@dp.message(PushEditState.waiting_for_text)
async def pedit_got_text(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.update_data(text=message.text)
    await state.set_state(PushEditState.choosing_field)
    await message.answer("✅ Текст обновлён.")
    await _show_edit_menu(message, state)


@dp.callback_query(PushEditState.choosing_field, F.data == "pedit_media")
async def pedit_media(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PushEditState.waiting_for_media)
    await callback.message.edit_text("✏️ Отправьте <b>новое фото или видео</b>:", parse_mode="HTML")
    await callback.answer()


@dp.callback_query(PushEditState.choosing_field, F.data == "pedit_save")
async def pedit_save(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    push_id = data.get("edit_push_id")
    await db.update_push(
        push_id=push_id,
        title=data.get("title", "Без названия"),
        content_type=data.get("content_type", "text"),
        send_weekday=data.get("send_weekday", 0),
        send_time=data.get("send_time", "09:00"),
        text=data.get("text"),
        file_id=data.get("file_id")
    )
    await state.clear()
    weekday = data.get("send_weekday", 0)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📬 К пушам",  callback_data="admin_pushes")],
        [InlineKeyboardButton(text="🛠 В панель", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(
        f"✅ <b>Пуш обновлён!</b>\n\n"
        f"📌 Название: <b>{data.get('title')}</b>\n"
        f"📎 Тип: {TYPE_LABELS.get(data.get('content_type'), '?')}\n"
        f"📅 День: <b>{WEEKDAY_NAMES[weekday]}</b>\n"
        f"🕐 Время: <b>{data.get('send_time')}</b> (Италия)\n\n"
        f"<i>Пуш снова активен.</i>",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer("✅ Сохранено!")


# ══════════════════════════════
#  УДАЛИТЬ ПУШ
# ══════════════════════════════

@dp.callback_query(F.data == "push_delete_list")
async def push_delete_list(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    pushes = await db.get_all_pushes()
    if not pushes:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_pushes")]
        ])
        try:
            await callback.message.edit_text(
                "🗑 <b>Удаление</b>\n\n<i>Нечего удалять.</i>",
                reply_markup=keyboard, parse_mode="HTML"
            )
        except Exception:
            pass
        await callback.answer()
        return

    buttons = []
    for push in pushes:
        pid, title, content_type, weekday, send_time, is_active = push
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {title[:25]} ({WEEKDAY_SHORT[weekday]} {send_time})",
            callback_data=f"push_confirm_del_{pid}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_pushes")])
    try:
        await callback.message.edit_text(
            "🗑 <b>Выберите пуш для удаления:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer()


@dp.callback_query(F.data.startswith("push_confirm_del_"))
async def push_confirm_delete(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    push_id = int(callback.data.replace("push_confirm_del_", ""))
    push = await db.get_push_by_id(push_id)
    if not push:
        await callback.answer("Не найден", show_alert=True)
        return
    pid, title, content_type, text, file_id, weekday, send_time, is_active = push
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Удалить",  callback_data=f"push_do_del_{pid}"),
            InlineKeyboardButton(text="❌ Отмена",   callback_data="push_delete_list")
        ]
    ])
    await callback.message.edit_text(
        f"⚠️ <b>Удалить пуш?</b>\n\n"
        f"📌 <b>{title}</b>\n"
        f"📅 {WEEKDAY_NAMES[weekday]}  🕐 {send_time}\n\n"
        f"<i>Действие необратимо.</i>",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("push_do_del_"))
async def push_do_delete(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    push_id = int(callback.data.replace("push_do_del_", ""))
    await db.delete_push(push_id)
    await callback.answer("✅ Удалён")
    await push_delete_list(callback)


# ─────────────────────────────────────────
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ РЕДАКТИРОВАНИЯ
# ─────────────────────────────────────────
def _parse_time(raw: str):
    try:
        parts = raw.split(":")
        assert len(parts) == 2
        hh, mm = int(parts[0]), int(parts[1])
        assert 0 <= hh <= 23 and 0 <= mm <= 59
        return f"{hh:02d}:{mm:02d}"
    except Exception:
        return None


async def _show_edit_menu(message: types.Message, state: FSMContext):
    data = await state.get_data()
    push_id = data.get("edit_push_id")
    title = data.get("title", "?")
    content_type = data.get("content_type", "?")
    weekday = data.get("send_weekday", 0)
    send_time = data.get("send_time", "?")
    text = data.get("text")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📌 Название",    callback_data="pedit_title")],
        [InlineKeyboardButton(text="📎 Тип контента",callback_data="pedit_type")],
        [InlineKeyboardButton(text="📅 День недели", callback_data="pedit_weekday")],
        [InlineKeyboardButton(text="🕐 Время",        callback_data="pedit_time")],
        [InlineKeyboardButton(text="✍️ Текст",        callback_data="pedit_text")],
        [InlineKeyboardButton(text="🖼 Медиафайл",    callback_data="pedit_media")],
        [InlineKeyboardButton(text="💾 Сохранить",    callback_data="pedit_save")],
        [InlineKeyboardButton(text="❌ Отмена",        callback_data="push_edit_list")]
    ])
    await message.answer(
        f"✏️ <b>Редактирование пуша #{push_id}</b>\n\n"
        f"📌 Название: <b>{title}</b>\n"
        f"📎 Тип: {TYPE_LABELS.get(content_type, '?')}\n"
        f"📅 День: <b>{WEEKDAY_NAMES[weekday]}</b>\n"
        f"🕐 Время: <b>{send_time}</b>\n"
        f"✍️ Текст: {text[:40] + '...' if text and len(text) > 40 else (text or '—')}\n\n"
        f"Что ещё изменить?",
        reply_markup=keyboard, parse_mode="HTML"
    )


async def _show_edit_menu_cb(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    push_id = data.get("edit_push_id")
    title = data.get("title", "?")
    content_type = data.get("content_type", "?")
    weekday = data.get("send_weekday", 0)
    send_time = data.get("send_time", "?")
    text = data.get("text")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📌 Название",    callback_data="pedit_title")],
        [InlineKeyboardButton(text="📎 Тип контента",callback_data="pedit_type")],
        [InlineKeyboardButton(text="📅 День недели", callback_data="pedit_weekday")],
        [InlineKeyboardButton(text="🕐 Время",        callback_data="pedit_time")],
        [InlineKeyboardButton(text="✍️ Текст",        callback_data="pedit_text")],
        [InlineKeyboardButton(text="🖼 Медиафайл",    callback_data="pedit_media")],
        [InlineKeyboardButton(text="💾 Сохранить",    callback_data="pedit_save")],
        [InlineKeyboardButton(text="❌ Отмена",        callback_data="push_edit_list")]
    ])
    try:
        await callback.message.edit_text(
            f"✏️ <b>Редактирование пуша #{push_id}</b>\n\n"
            f"📌 Название: <b>{title}</b>\n"
            f"📎 Тип: {TYPE_LABELS.get(content_type, '?')}\n"
            f"📅 День: <b>{WEEKDAY_NAMES[weekday]}</b>\n"
            f"🕐 Время: <b>{send_time}</b>\n"
            f"✍️ Текст: {text[:40] + '...' if text and len(text) > 40 else (text or '—')}\n\n"
            f"Что ещё изменить?",
            reply_markup=keyboard, parse_mode="HTML"
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
#  ЗАПУСК
# ═══════════════════════════════════════════════════════════
async def main():
    await db.create_table()
    scheduler.add_job(
        send_scheduled_push,
        CronTrigger(minute="*", timezone=ITALY_TZ)
    )
    scheduler.start()
    print("🚀 Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Бот остановлен.")