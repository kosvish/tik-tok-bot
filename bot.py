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
from aiogram.exceptions import TelegramBadRequest

from lexicon import LEXICON
from database import Database

# --- НАСТРОЙКИ ---
ADMIN_ID = 636775647
CHANNEL_ID = "-1003890716920"

db = Database('bot.db')
logging.basicConfig(level=logging.INFO)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- СОСТОЯНИЯ ---
class WithdrawState(StatesGroup):
    waiting_for_wallet = State()


class VideoState(StatesGroup):
    waiting_for_click = State()
    waiting_for_comment = State()


class AdminState(StatesGroup):
    waiting_for_broadcast_text = State()


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def delete_message_after(message: types.Message, sleep_time: int):
    await asyncio.sleep(sleep_time)
    try:
        await message.delete()
    except:
        pass


# Временный хендлер для получения file_id видео (Скрытый функционал для тебя)
@dp.message(F.video)
async def get_video_id(message: types.Message):
    video_id = message.video.file_id
    await message.reply(
        f"✅ <b>Твой File ID:</b>\n\n"
        f"<code>{video_id}</code>\n\n"
        f"Скопируй эту строку в список в lexicon.py",
        parse_mode="HTML"
    )


# --- ЛОГИКА ОТПРАВКИ ЗАДАНИЙ ---
async def send_video_task(message: types.Message, current_video: int, balance: float, state: FSMContext,
                          edit: bool = True):
    user_data = await state.get_data()

    # Формируем очередь заданий
    tasks_queue = user_data.get('tasks_queue')
    if not tasks_queue:
        tasks_queue = ['like'] * 5 + ['comment'] * 5
        random.shuffle(tasks_queue)

        # ГАРАНТИЯ: Делаем первое видео всегда с ЛАЙКОМ
        if tasks_queue[0] == 'comment':
            first_like_idx = tasks_queue.index('like')
            tasks_queue[0], tasks_queue[first_like_idx] = tasks_queue[first_like_idx], tasks_queue[0]

        await state.update_data(tasks_queue=tasks_queue)

    task_type = tasks_queue[current_video - 1]

    # Настройки задания
    if task_type == 'like':
        reward = random.choice([0.70, 0.90, 1.20])
        if message.chat.id == ADMIN_ID:
            duration = 0  # Для тебя задержки нет
        else:
            duration = 10  # Для мамонтов 10 сек
        task_data = LEXICON['task_like_dislike']

        caption = LEXICON['video_task'].format(
            current=current_video,
            reward=f"{reward:.2f}",
            task_text=task_data['text'],
            balance=f"{balance:.2f}"
        )

        inline_kb = [
            [
                InlineKeyboardButton(text=f"👍 (+{reward:.2f}€)", callback_data="task_done"),
                InlineKeyboardButton(text=f"👎 (+{reward:.2f}€)", callback_data="task_done")
            ],
            [InlineKeyboardButton(text=LEXICON['btn_finish'], callback_data="main_menu")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=inline_kb)
        await state.set_state(VideoState.waiting_for_click)

    else:
        reward = random.choice([2.50, 3.00, 3.50])
        if message.chat.id == ADMIN_ID:
            duration = 0  # Для тебя задержки нет
        else:
            duration = 10  # Для мамонтов 10 сек
        task_data = LEXICON['task_comment']

        caption = LEXICON['video_task'].format(
            current=current_video,
            reward=f"{reward:.2f}",
            task_text=task_data['text'],
            balance=f"{balance:.2f}"
        )

        inline_kb = [[InlineKeyboardButton(text=LEXICON['btn_finish'], callback_data="main_menu")]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=inline_kb)
        await state.set_state(VideoState.waiting_for_comment)

    # Таймер защиты
    unlock_time = time.time() + duration
    await state.update_data(unlock_time=unlock_time, current_reward=reward)

    video_id = LEXICON['videos'][current_video - 1]

    # Отправка
    if edit:
        try:
            await message.edit_media(
                media=InputMediaVideo(media=video_id, caption=caption, parse_mode="HTML"),
                reply_markup=keyboard
            )
        except Exception:
            try:
                await message.delete()
            except:
                pass
            await message.answer_video(video=video_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer_video(video=video_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")


# --- СТАРТ И МЕНЮ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "amico"

    if not db.user_exists(user_id):
        db.add_user(user_id, user_name)
        await state.clear()

        text = LEXICON['welcome_msg'].format(name=user_name)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=LEXICON['btn_informed'], callback_data="start_earning")]
        ])
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        balance, current_video = db.get_user(user_id)
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
            # Пытаемся плавно заменить текст (если это было текстовое сообщение)
            await message.edit_text(LEXICON['main_menu_text'], reply_markup=keyboard)
        except Exception:
            # Если это было ВИДЕО (Telegram выдаст ошибку) - удаляем его агрессивно
            try:
                await message.delete()
            except Exception:
                pass  # Игнорируем, если сообщение уже удалено
            # Присылаем меню чистым новым сообщением
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
    user_data = db.get_user(user_id)

    # Защита от сбоев БД
    if not user_data:
        balance, current_video = 0.0, 1
    else:
        balance, current_video = user_data
        current_video = int(current_video)  # Жестко фиксируем как число

    if current_video <= 10:
        await callback.answer("Caricamento video...")
        await state.update_data(balance=balance, current_video=current_video)

        # Удаляем старое меню, чтобы чат был чистым
        try:
            await callback.message.delete()
        except:
            pass

        # Отправляем видео НОВЫМ сообщением (edit=False)
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


# --- ОБРАБОТКА ЗАДАНИЙ ---
# --- ОБРАБОТКА ЛАЙКОВ/ДИЗЛАЙКОВ ---
@dp.callback_query(VideoState.waiting_for_click, F.data == "task_done")
async def process_task_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    unlock_time = data.get("unlock_time", 0)

    # Защита от быстрых кликов
    if time.time() < unlock_time:
        await callback.answer(LEXICON['alert_too_fast'], show_alert=True)
        return

    balance = data.get("balance", 0.0)
    current_reward = data.get("current_reward", 1.0)
    current_video = data.get("current_video", 1)

    new_balance = round(balance + current_reward, 2)
    new_video = current_video + 1

    await callback.answer(f"✅ +{current_reward:.2f}€!", show_alert=False)

    # --- ФИНАЛ: ЕСЛИ ЭТО БЫЛО 10-Е ВИДЕО ---
    if new_video > 10:
        total_balance = round(new_balance + 50.0, 2)

        # 1. ЖЕЛЕЗОБЕТОННО СОХРАНЯЕМ В БАЗУ (до отправки текста!)
        db.update_user(callback.from_user.id, total_balance, new_video)
        await state.update_data(balance=total_balance)
        await state.set_state(None)

        try:
            await callback.message.delete()
        except:
            pass

        # 2. Безопасная отправка (защита от краша словаря)
        try:
            text = LEXICON['finish_task'].format(balance=new_balance, total=total_balance)
        except Exception:
            text = f"🎉 Hai completato tutto! Hai guadagnato {new_balance}€ + 50€ di bonus! Totale: {total_balance}€"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=LEXICON.get('btn_menu', 'Menu'), callback_data="main_menu")]
        ])

        try:
            await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)

    # --- ЕСЛИ ЕЩЕ ЕСТЬ ВИДЕО (1-9) ---
    else:
        db.update_user(callback.from_user.id, new_balance, new_video)
        await state.update_data(balance=new_balance, current_video=new_video)
        await send_video_task(callback.message, new_video, new_balance, state)


# --- ОБРАБОТКА КОММЕНТАРИЕВ ---
@dp.message(VideoState.waiting_for_comment)
async def process_comment_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    unlock_time = data.get("unlock_time", 0)
    current_time = time.time()

    # Защита от быстрого комментария
    if current_time < unlock_time:
        remaining = int(unlock_time - current_time)
        try:
            await message.delete()
        except:
            pass
        warn = await message.answer(f"⏳ Non hai guardato tutto il video! Aspetta ancora {remaining} sec.")
        asyncio.create_task(delete_message_after(warn, 3))
        return

    # Защита от короткого комментария
    if len(message.text) < 15:
        try:
            await message.delete()
        except:
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
    except:
        pass

    # --- ФИНАЛ: ЕСЛИ ЭТО БЫЛО 10-Е ВИДЕО ---
    if new_video > 10:
        total_balance = round(new_balance + 50.0, 2)

        # 1. ЖЕЛЕЗОБЕТОННО СОХРАНЯЕМ В БАЗУ (до отправки текста!)
        db.update_user(message.from_user.id, total_balance, new_video)
        await state.update_data(balance=total_balance)
        await state.set_state(None)

        # 2. Безопасная отправка сообщения (защита от краша словаря)
        try:
            text = LEXICON['finish_task'].format(balance=new_balance, total=total_balance)
        except Exception:
            # Если в lexicon.py ошибка, бот выдаст этот резервный текст и пойдет дальше
            text = f"🎉 Hai completato tutto! Hai guadagnato {new_balance}€ + 50€ di bonus! Totale: {total_balance}€"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=LEXICON.get('btn_menu', 'Menu'), callback_data="main_menu")]
        ])

        try:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await message.answer(text, reply_markup=keyboard)

    # --- ЕСЛИ ЕЩЕ ЕСТЬ ВИДЕО (1-9) ---
    else:
        db.update_user(message.from_user.id, new_balance, new_video)
        await state.update_data(balance=new_balance, current_video=new_video)
        await send_video_task(message, new_video, new_balance, state, edit=False)


@dp.message(Command("reset"))  # Если у тебя роутеры, замени dp на router
async def cmd_reset(message: types.Message, state: FSMContext):
    # Обнуляем баланс и ставим 1-е видео
    db.update_user(message.from_user.id, 0.0, 1)

    # Очищаем память машины состояний
    await state.clear()

    await message.answer("🔄 <b>Прогресс сброшен!</b>\nТы на 1-м видео с балансом 0€.\nНажми /start", parse_mode="HTML")


# Чит-код 2: Прыжок сразу на 10-е видео
@dp.message(Command("jump"))  # Если у тебя роутеры, замени dp на router
async def cmd_jump(message: types.Message, state: FSMContext):
    # Ставим 10-е видео и баланс, например, 45 евро
    db.update_user(message.from_user.id, 45.0, 10)

    # Сохраняем это в память (чтобы логика бота подхватила)
    await state.update_data(balance=45.0, current_video=10)

    await message.answer(
        "🦘 <b>Прыжок совершен!</b>\nТы на 10-м видео. Жми кнопку заработка и проверяй финальное задание!",
        parse_mode="HTML")


@dp.callback_query(F.data == "profile")
async def process_profile(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name
    # Получаем юзернейм или ставим заглушку, если его нет
    username = callback.from_user.username or "Senza_username"

    user_data = db.get_user(user_id)
    if user_data:
        balance, current_video = user_data
    else:
        balance, current_video = 0.0, 1

    video_count = min(current_video - 1, 10)

    text = LEXICON['profile_text'].format(
        name=user_name,
        username=username,
        balance=f"{balance:.2f}",
        video_count=video_count
    )

    # Кнопки как на скрине профиля
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
        except:
            pass
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    await callback.answer()


@dp.callback_query(F.data == "withdraw")
async def process_withdraw(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    # На всякий случай берем актуальный баланс из БД
    user_data = db.get_user(callback.from_user.id)
    balance = user_data[0] if user_data else data.get("balance", 0)

    text = LEXICON['withdraw_text'].format(balance=f"{balance:.2f}")

    # Расставляем кнопки в два ряда, как на скрине
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
    # Универсальный текст с гарантией безопасности
    text = LEXICON['ask_wallet_generic']

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="withdraw")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
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
                [InlineKeyboardButton(text="📱 Contatta il Manager", url="https://t.me/maximilian_muchos")],
                [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="main_menu")]
            ])
            await callback.message.edit_text(LEXICON['sub_success'], reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        await callback.answer("⚠️ Errore tecnico. Riprova più tardi.", show_alert=True)


# ЗАГЛУШКИ
# --- ПАРТНЕРЫ (ОДНА ССЫЛКА НА КАНАЛ) ---
@dp.callback_query(F.data == "partners")
async def process_partners_menu(callback: types.CallbackQuery, state: FSMContext):
    text = LEXICON['partners_text']

    # Оставляем только одну кнопку-ссылку и кнопку возврата
    # ВАЖНО: замени url="..." на ссылку своего канала
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON['btn_partner_channel'], url="https://t.me/+Fdt1AaN0Pu9iNGNi")],
        [InlineKeyboardButton(text=LEXICON['btn_back'], callback_data="main_menu")]
    ])

    # Пытаемся красиво отредактировать сообщение
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        # Если не вышло, удаляем и шлем заново
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    await callback.answer()


# --- АДМИН-ПАНЕЛЬ ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="❌ Выход", callback_data="main_menu")]
    ])
    await message.answer("🛠 <b>Панель администратора</b>\nВыберите действие:", reply_markup=keyboard, parse_mode="HTML")


@dp.callback_query(F.data == "admin_stats")
async def show_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    total_users, total_money = db.get_stats()
    now = datetime.datetime.now().strftime("%H:%M:%S")
    text = (
        f"📊 <b>Текущая статистика:</b>\n\n"
        f"👤 Всего пользователей: {total_users}\n"
        f"💰 Начислено евро (всего): {total_money:.2f} €\n\n"
        f"🕒 <i>Обновлено в: {now}</i>"
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=callback.message.reply_markup)
    except TelegramBadRequest:
        await callback.answer("Данные уже актуальны")


@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    instruction_text = (
        "📝 <b>Отправьте текст сообщения для распространения:</b>\n\n"
        "Puoi usare l'HTML. Tutti gli utenti riceveranno questo messaggio."
    )
    await callback.message.answer(instruction_text, parse_mode="HTML")
    await state.set_state(AdminState.waiting_for_broadcast_text)
    await callback.answer()


@dp.message(AdminState.waiting_for_broadcast_text)
async def perform_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    users = db.get_all_users()
    count = 0
    error_count = 0
    status_msg = await message.answer(f"🚀 Начинаю рассылку на {len(users)} чел...")
    for user_id in users:
        try:
            await message.send_copy(chat_id=user_id)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            error_count += 1
    await status_msg.edit_text(f"✅ <b>Рассылка завершена!</b>\n\n"
                               f"📈 Доставлено: {count}\n"
                               f"📉 Заблокировали бота: {error_count}", parse_mode="HTML")
    await state.clear()


async def main():
    print("🚀 Бот запущен! Код отшлифован до блеска.")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Бот остановлен вручную.")
