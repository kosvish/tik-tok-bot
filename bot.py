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
ADMIN_ID = 636775647
CHANNEL_ID = "-1003890716920"
ITALY_TZ = pytz.timezone("Europe/Rome")

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


def admin_only(func):
    """Декоратор-заглушка: проверяем ADMIN_ID внутри каждого хендлера."""
    return func


# ─────────────────────────────────────────
#  ПЛАНИРОВЩИК ПУШЕЙ
# ─────────────────────────────────────────
async def send_scheduled_push():
    """Вызывается каждую минуту. Проверяет, есть ли пуши на текущее время."""
    now_italy = datetime.datetime.now(ITALY_TZ)
    current_time = now_italy.strftime("%H:%M")

    pushes = await db.get_active_pushes_for_time(current_time)
    if not pushes:
        return

    users = await db.get_all_users()
    for push in pushes:
        push_id, title, content_type, text, file_id, send_time = push
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

        logging.info(f"[PUSH #{push_id}] «{title}» отправлен: {sent}, ошибок: {errors}")
        # Уведомляем админа
        try:
            await bot.send_message(
                ADMIN_ID,
                f"📬 <b>Пуш отправлен!</b>\n\n"
                f"📌 Название: <b>{title}</b>\n"
                f"✅ Доставлено: {sent}\n"
                f"❌ Ошибок: {errors}",
                parse_mode="HTML"
            )
        except Exception:
            pass


async def _send_push_to_user(user_id: int, content_type: str, text: str, file_id: str):
    """Отправить один пуш одному пользователю в зависимости от типа."""
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
#  ПОЛУЧЕНИЕ file_id (скрытый инструмент)
# ─────────────────────────────────────────
@dp.message(F.video)
async def get_video_id(message: types.Message, state: FSMContext):
    # Если админ добавляет видео для пуша — обрабатываем в PushState
    current_state = await state.get_state()
    if current_state == PushState.waiting_for_media:
        file_id = message.video.file_id
        await state.update_data(file_id=file_id)
        push_data = await state.get_data()
        content_type = push_data.get("content_type")
        if content_type == "video":
            # Только видео — сразу к времени
            await state.set_state(PushState.waiting_for_time)
            await message.answer(
                "✅ Видео принято!\n\n"
                "🕐 <b>Введите время отправки</b> по итальянскому времени в формате <code>ЧЧ:ММ</code>\n"
                "Например: <code>10:00</code>",
                parse_mode="HTML"
            )
        else:
            # video_text — нужен ещё текст
            await state.set_state(PushState.waiting_for_text)
            await message.answer(
                "✅ Видео принято!\n\n"
                "✍️ Теперь введите <b>текст</b> для подписи к видео:",
                parse_mode="HTML"
            )
        return

    # Обычная выдача file_id (если не в состоянии пуша)
    if message.from_user.id == ADMIN_ID:
        await message.reply(
            f"✅ <b>File ID видео:</b>\n\n<code>{message.video.file_id}</code>",
            parse_mode="HTML"
        )


@dp.message(F.photo)
async def get_photo_id(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == PushState.waiting_for_media:
        file_id = message.photo[-1].file_id
        await state.update_data(file_id=file_id)
        push_data = await state.get_data()
        content_type = push_data.get("content_type")
        if content_type == "photo":
            await state.set_state(PushState.waiting_for_time)
            await message.answer(
                "✅ Фото принято!\n\n"
                "🕐 <b>Введите время отправки</b> по итальянскому времени в формате <code>ЧЧ:ММ</code>\n"
                "Например: <code>10:00</code>",
                parse_mode="HTML"
            )
        else:
            await state.set_state(PushState.waiting_for_text)
            await message.answer(
                "✅ Фото принято!\n\n"
                "✍️ Теперь введите <b>текст</b> для подписи к фото:",
                parse_mode="HTML"
            )
        return

    if message.from_user.id == ADMIN_ID:
        await message.reply(
            f"✅ <b>File ID фото:</b>\n\n<code>{message.photo[-1].file_id}</code>",
            parse_mode="HTML"
        )


# ─────────────────────────────────────────
#  ЛОГИКА ОТПРАВКИ ЗАДАНИЙ (без изменений)
# ─────────────────────────────────────────
async def send_video_task(message: types.Message, current_video: int, balance: float,
                          state: FSMContext, edit: bool = True):
    user_data = await state.get_data()

    tasks_queue = user_data.get('tasks_queue')
    if not tasks_queue:
        tasks_queue = ['like'] * 5 + ['comment'] * 5
        random.shuffle(tasks_queue)
        if tasks_queue[0] == 'comment':
            first_like_idx = tasks_queue.index('like')
            tasks_queue[0], tasks_queue[first_like_idx] = tasks_queue[first_like_idx], tasks_queue[0]
        await state.update_data(tasks_queue=tasks_queue)

    task_type = tasks_queue[current_video - 1]

    if task_type == 'like':
        reward = random.choice([0.70, 0.90, 1.20])
        duration = 0 if message.chat.id == ADMIN_ID else 10
        task_data = LEXICON['task_like_dislike']
        caption = LEXICON['video_task'].format(
            current=current_video, reward=f"{reward:.2f}",
            task_text=task_data['text'], balance=f"{balance:.2f}"
        )
        inline_kb = [
            [
                InlineKeyboardButton(text=f"👍 (+{reward:.2f}€)", callback_data="task_done"),
                InlineKeyboardButton(text=f"👎 (+{reward:.2f}€)", callback_data="task_done"),
            ],
            [InlineKeyboardButton(text=LEXICON['btn_finish'], callback_data="main_menu")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=inline_kb)
        await state.set_state(VideoState.waiting_for_click)
    else:
        reward = random.choice([2.50, 3.00, 3.50])
        duration = 0 if message.chat.id == ADMIN_ID else 10
        task_data = LEXICON['task_comment']
        caption = LEXICON['video_task'].format(
            current=current_video, reward=f"{reward:.2f}",
            task_text=task_data['text'], balance=f"{balance:.2f}"
        )
        inline_kb = [[InlineKeyboardButton(text=LEXICON['btn_finish'], callback_data="main_menu")]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=inline_kb)
        await state.set_state(VideoState.waiting_for_comment)

    unlock_time = time.time() + duration
    await state.update_data(unlock_time=unlock_time, current_reward=reward)
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
        text = LEXICON['welcome_msg'].format(name=user_name)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=LEXICON['btn_informed'], callback_data="start_earning")]
        ])
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        balance, current_video = await db.get_user(user_id)
        if current_video <= 10:
            await message.answer("Bentornato! 📈 Continuiamo da dove avevi interrotto.")
            await state.update_data(balance=balance, current_video=current_video)
            await send_video_task(message, current_video, balance, state, edit=False)
        else:
            await state.update_data(balance=balance, current_video=current_video)
            await show_main_menu(message, edit=False)


async def show_main_menu(message: types.Message, edit: bool = True):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON['btn_earn'], callback_data="earn")],
        [InlineKeyboardButton(text=LEXICON['btn_profile'], callback_data="profile")],
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

    if current_video <= 10:
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
            [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="main_menu")]
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

    balance = data.get("balance", 0.0)
    current_reward = data.get("current_reward", 1.0)
    current_video = data.get("current_video", 1)
    new_balance = round(balance + current_reward, 2)
    new_video = current_video + 1

    await callback.answer(f"✅ +{current_reward:.2f}€!", show_alert=False)

    if new_video > 10:
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
            text = f"🎉 Completato! +{new_balance}€ + 20€ bonus = {total_balance}€"
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
        warn = await message.answer(f"⏳ Non hai guardato tutto il video! Aspetta ancora {remaining} sec.")
        task = asyncio.create_task(delete_message_after(warn, 3))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        return

    if len(message.text or "") < 15:
        try:
            await message.delete()
        except Exception:
            pass
        warn = await message.answer("⚠️ Il tuo commento è troppo corto! Scrivi almeno 15 caratteri.")
        asyncio.create_task(delete_message_after(warn, 3))
        return

    balance = data.get("balance", 0.0)
    current_reward = data.get("current_reward", 1.0)
    current_video = data.get("current_video", 1)
    new_balance = round(balance + current_reward, 2)
    new_video = current_video + 1

    try:
        await message.delete()
    except Exception:
        pass

    if new_video > 10:
        total_balance = round(new_balance + 20.0, 2)
        await db.update_user(message.from_user.id, total_balance, new_video)
        await state.update_data(balance=total_balance)
        await state.set_state(None)
        try:
            text = LEXICON['finish_task'].format(balance=new_balance, total=total_balance)
        except Exception:
            text = f"🎉 Completato! +{new_balance}€ + 20€ bonus = {total_balance}€"
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
    await message.answer("🔄 <b>Прогресс сброшен!</b>\nНажми /start", parse_mode="HTML")


@dp.message(Command("jump"))
async def cmd_jump(message: types.Message, state: FSMContext):
    await db.update_user(message.from_user.id, 45.0, 10)
    await state.update_data(balance=45.0, current_video=10)
    await message.answer("🦘 <b>Прыжок совершен!</b> Ты на 10-м видео.", parse_mode="HTML")


# ─────────────────────────────────────────
#  ПРОФИЛЬ / ВЫВОД / ПАРТНЁРЫ
# ─────────────────────────────────────────
@dp.callback_query(F.data == "profile")
async def process_profile(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name
    username = callback.from_user.username or "Senza_username"
    user_data = await db.get_user(user_id)
    balance, current_video = user_data if user_data else (0.0, 1)
    video_count = min(current_video - 1, 10)
    text = LEXICON['profile_text'].format(
        name=user_name, username=username,
        balance=f"{balance:.2f}", video_count=video_count
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
    data = await state.get_data()
    user_data = await db.get_user(callback.from_user.id)
    balance = user_data[0] if user_data else data.get("balance", 0)
    text = LEXICON['withdraw_text'].format(balance=f"{balance:.2f}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=LEXICON['btn_phone'], callback_data="pay_phone"),
            InlineKeyboardButton(text=LEXICON['btn_paypal'], callback_data="pay_paypal")
        ],
        [
            InlineKeyboardButton(text=LEXICON['btn_binance'], callback_data="pay_binance"),
            InlineKeyboardButton(text=LEXICON['btn_card'], callback_data="pay_card")
        ],
        [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="main_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
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
    details = message.text
    if len(details) < 8:
        await message.answer(LEXICON['invalid_details'], parse_mode="HTML")
        return
    processing_msg = await message.answer(LEXICON['processing_1'], parse_mode="HTML")
    await asyncio.sleep(2)
    await processing_msg.edit_text(LEXICON['processing_2'], parse_mode="HTML")
    await asyncio.sleep(2)
    data = await state.get_data()
    balance = data.get("balance", 0)
    text = LEXICON['withdraw_trap'].format(balance=f"{balance:.2f}", details=details)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON['btn_check_sub_now'], callback_data="verify_subscription")],
        [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="main_menu")]
    ])
    await processing_msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
    await state.set_state(None)


@dp.callback_query(F.data == "verify_subscription")
async def check_user_subscription(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        member = await callback.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ['left', 'kicked']:
            await callback.answer("❌ Non sei ancora iscritto!", show_alert=True)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=LEXICON['btn_subscribe'], url="https://t.me/+Fdt1AaN0Pu9iNGNi")],
                [InlineKeyboardButton(text=LEXICON['btn_check_sub_now'], callback_data="verify_subscription")]
            ])
            await callback.message.edit_text(LEXICON['sub_required_text'], reply_markup=keyboard, parse_mode="HTML")
        else:
            await callback.answer("✅ Verifica completata!", show_alert=False)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📱 Contatta il Manager", url="https://t.me/monica_guadagno")],
                [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="main_menu")]
            ])
            await callback.message.edit_text(LEXICON['sub_success'], reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        await callback.answer("⚠️ Errore tecnico. Riprova più tardi.", show_alert=True)


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
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📬 Пуш-рассылки", callback_data="admin_pushes")],
        [InlineKeyboardButton(text="📢 Быстрая рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="❌ Выход", callback_data="main_menu")]
    ])


@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
        reply_markup=_admin_keyboard(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "admin_panel")
async def back_to_admin(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.clear()
    try:
        await callback.message.edit_text(
            "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
            reply_markup=_admin_keyboard(),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
            reply_markup=_admin_keyboard(),
            parse_mode="HTML"
        )
    await callback.answer()


# ───── СТАТИСТИКА ─────
@dp.callback_query(F.data == "admin_stats")
async def show_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    total_users, total_money = await db.get_stats()
    pushes = await db.get_all_pushes()
    active_pushes = sum(1 for p in pushes if p[4] == 1)
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
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except TelegramBadRequest:
        await callback.answer("Данные уже актуальны ✅")


# ───── БЫСТРАЯ РАССЫЛКА ─────
@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer(
        "📢 <b>Быстрая рассылка</b>\n\n"
        "Отправьте сообщение (текст, фото, видео) — оно уйдёт всем пользователям <b>немедленно</b>.",
        parse_mode="HTML"
    )
    await state.set_state(AdminState.waiting_for_broadcast_text)
    await callback.answer()


@dp.message(AdminState.waiting_for_broadcast_text)
async def perform_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
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
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📈 Доставлено: {count}\n"
        f"📉 Ошибок: {errors}",
        parse_mode="HTML"
    )
    await state.clear()


# ═══════════════════════════════════════════════════════════
#  П У Ш - Р А С С Ы Л К И  (меню)
# ═══════════════════════════════════════════════════════════

@dp.callback_query(F.data == "admin_pushes")
async def admin_pushes_menu(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить пуш", callback_data="push_add")],
        [InlineKeyboardButton(text="📋 Список пушей", callback_data="push_list")],
        [InlineKeyboardButton(text="🗑 Удалить пуш", callback_data="push_delete_list")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(
        "📬 <b>Пуш-рассылки</b>\n\n"
        "Здесь вы управляете автоматическими рассылками.\n"
        "Пуши отправляются всем пользователям в указанное время по <b>итальянскому времени</b>.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


# ───── ДОБАВИТЬ ПУШ: шаг 1 — название ─────
@dp.callback_query(F.data == "push_add")
async def push_add_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await state.set_state(PushState.waiting_for_title)
    await callback.message.edit_text(
        "➕ <b>Новый пуш — шаг 1/3</b>\n\n"
        "Введите <b>название</b> пуша (только для вас, пользователи не видят).\n"
        "Например: <i>Утренний пуш</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message(PushState.waiting_for_title)
async def push_got_title(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(PushState.waiting_for_type)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Только текст", callback_data="ptype_text")],
        [InlineKeyboardButton(text="🖼 Только фото", callback_data="ptype_photo")],
        [InlineKeyboardButton(text="🎬 Только видео", callback_data="ptype_video")],
        [InlineKeyboardButton(text="🖼+✍️ Фото + текст", callback_data="ptype_photo_text")],
        [InlineKeyboardButton(text="🎬+✍️ Видео + текст", callback_data="ptype_video_text")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_pushes")]
    ])
    await message.answer(
        "➕ <b>Новый пуш — шаг 2/3</b>\n\n"
        "Выберите <b>тип контента</b>:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ───── шаг 2 — тип контента ─────
@dp.callback_query(F.data.startswith("ptype_"))
async def push_got_type(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    content_type = callback.data.replace("ptype_", "")
    await state.update_data(content_type=content_type)

    if content_type == "text":
        await state.set_state(PushState.waiting_for_text)
        await callback.message.edit_text(
            "✍️ <b>Введите текст</b> пуша:\n\n"
            "Поддерживается HTML-разметка: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, <code>&lt;a href&gt;</code>",
            parse_mode="HTML"
        )
    elif content_type in ("photo", "video"):
        await state.set_state(PushState.waiting_for_media)
        media_word = "фото" if content_type == "photo" else "видео"
        await callback.message.edit_text(
            f"📎 <b>Отправьте {media_word}</b> для пуша:",
            parse_mode="HTML"
        )
    else:
        # photo_text / video_text
        await state.set_state(PushState.waiting_for_media)
        media_word = "фото" if content_type == "photo_text" else "видео"
        await callback.message.edit_text(
            f"📎 <b>Отправьте {media_word}</b> для пуша:",
            parse_mode="HTML"
        )
    await callback.answer()


# ───── шаг 2б — текст (для типов с текстом) ─────
@dp.message(PushState.waiting_for_text)
async def push_got_text(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(text=message.text)
    await state.set_state(PushState.waiting_for_time)
    await message.answer(
        "🕐 <b>Шаг 3/3 — Время отправки</b>\n\n"
        "Введите время в формате <code>ЧЧ:ММ</code> по <b>итальянскому времени</b>.\n"
        "Например: <code>09:00</code>",
        parse_mode="HTML"
    )


# ───── шаг 3 — время ─────
@dp.message(PushState.waiting_for_time)
async def push_got_time(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    raw_time = message.text.strip()
    # Валидация формата ЧЧ:ММ
    try:
        parts = raw_time.split(":")
        assert len(parts) == 2
        hh, mm = int(parts[0]), int(parts[1])
        assert 0 <= hh <= 23 and 0 <= mm <= 59
        send_time = f"{hh:02d}:{mm:02d}"
    except Exception:
        await message.answer(
            "❌ Неверный формат! Введите время как <code>ЧЧ:ММ</code>, например <code>10:30</code>",
            parse_mode="HTML"
        )
        return

    data = await state.get_data()
    title = data.get("title", "Без названия")
    content_type = data.get("content_type", "text")
    text = data.get("text")
    file_id = data.get("file_id")

    await db.add_push(
        title=title,
        content_type=content_type,
        send_time=send_time,
        text=text,
        file_id=file_id
    )
    await state.clear()

    # Красивое резюме
    type_labels = {
        "text": "✍️ Только текст",
        "photo": "🖼 Только фото",
        "video": "🎬 Только видео",
        "photo_text": "🖼+✍️ Фото + текст",
        "video_text": "🎬+✍️ Видео + текст",
    }
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📬 К пушам", callback_data="admin_pushes")],
        [InlineKeyboardButton(text="🛠 В панель", callback_data="admin_panel")]
    ])
    await message.answer(
        f"✅ <b>Пуш успешно создан!</b>\n\n"
        f"📌 Название: <b>{title}</b>\n"
        f"📎 Тип: {type_labels.get(content_type, content_type)}\n"
        f"🕐 Время: <b>{send_time}</b> (Италия)\n\n"
        f"<i>Пуш будет отправляться всем пользователям каждый день в {send_time}.</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ───── СПИСОК ПУШЕЙ ─────
@dp.callback_query(F.data == "push_list")
async def push_list(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    pushes = await db.get_all_pushes()

    if not pushes:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить", callback_data="push_add")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_pushes")]
        ])
        await callback.message.edit_text(
            "📋 <b>Список пушей</b>\n\n<i>Пушей пока нет. Добавьте первый!</i>",
            reply_markup=keyboard, parse_mode="HTML"
        )
        await callback.answer()
        return

    type_icons = {
        "text": "✍️", "photo": "🖼", "video": "🎬",
        "photo_text": "🖼✍️", "video_text": "🎬✍️"
    }
    lines = ["📋 <b>Все пуши:</b>\n"]
    buttons = []
    for push in pushes:
        pid, title, content_type, send_time, is_active = push
        status = "🟢" if is_active else "🔴"
        icon = type_icons.get(content_type, "📎")
        lines.append(f"{status} {icon} <b>{title}</b> — {send_time}")
        # Кнопка вкл/выкл для каждого пуша
        toggle_text = f"{'⏸' if is_active else '▶️'} {title[:20]}"
        buttons.append([InlineKeyboardButton(text=toggle_text, callback_data=f"push_toggle_{pid}")])

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_pushes")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("push_toggle_"))
async def push_toggle(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    push_id = int(callback.data.replace("push_toggle_", ""))
    new_status = await db.toggle_push(push_id)
    status_text = "включён 🟢" if new_status == 1 else "отключён 🔴"
    await callback.answer(f"Пуш #{push_id} {status_text}", show_alert=False)
    # Обновляем список
    await push_list(callback)


# ───── УДАЛЕНИЕ ПУШЕЙ ─────
@dp.callback_query(F.data == "push_delete_list")
async def push_delete_list(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    pushes = await db.get_all_pushes()

    if not pushes:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_pushes")]
        ])
        await callback.message.edit_text(
            "🗑 <b>Удаление пушей</b>\n\n<i>Нечего удалять.</i>",
            reply_markup=keyboard, parse_mode="HTML"
        )
        await callback.answer()
        return

    buttons = []
    for push in pushes:
        pid, title, content_type, send_time, is_active = push
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {title[:25]} ({send_time})",
                callback_data=f"push_confirm_del_{pid}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_pushes")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "🗑 <b>Удаление пушей</b>\n\nВыберите пуш для удаления:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("push_confirm_del_"))
async def push_confirm_delete(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    push_id = int(callback.data.replace("push_confirm_del_", ""))
    push = await db.get_push_by_id(push_id)
    if not push:
        await callback.answer("Пуш не найден", show_alert=True)
        return
    pid, title, content_type, text, file_id, send_time, is_active = push
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"push_do_del_{pid}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="push_delete_list")
        ]
    ])
    await callback.message.edit_text(
        f"⚠️ <b>Удалить пуш?</b>\n\n"
        f"📌 <b>{title}</b>\n"
        f"🕐 Время: {send_time}\n\n"
        f"<i>Это действие нельзя отменить.</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("push_do_del_"))
async def push_do_delete(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    push_id = int(callback.data.replace("push_do_del_", ""))
    await db.delete_push(push_id)
    await callback.answer("✅ Пуш удалён", show_alert=False)
    await push_delete_list(callback)


# ═══════════════════════════════════════════════════════════
#  ЗАПУСК
# ═══════════════════════════════════════════════════════════
async def main():
    await db.create_table()

    # Планировщик: каждую минуту проверяем пуши
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
        print("🛑 Бот остановлен вручную.")