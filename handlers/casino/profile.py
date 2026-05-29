import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .base import (
    get_bot, get_db, get_user, create_user, update_balance, update_blackjack_balance, get_username,
    is_casino_admin, has_perm, is_owner, get_users_with_perm,
    DepositState, PaymentProvideState, WithdrawState, AdminAction,
    ADMIN_ID, INITIAL_BLACKJACK_BALANCE, INITIAL_BOT_BALANCE, logger,
)

router = Router()


@router.message(Command("профиль"))
@router.message(Command("profile"))
async def cmd_profile(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await create_user(message.from_user)
        user = await get_user(message.from_user.id)

    if message.chat.type != "private":
        await message.reply("ℹ️ Для просмотра профиля и пополнения баланса перейдите в личные сообщения с ботом.")
        return

    bj_bal = user.get("blackjack_balance")
    if bj_bal is None:
        bj_bal = INITIAL_BLACKJACK_BALANCE
    bbot = user.get("bot_balance")
    if bbot is None:
        bbot = INITIAL_BOT_BALANCE
    text = (
        f"<b>📊 Профиль игрока</b> {message.from_user.first_name}\n\n"
        f"┃ 🆔 ID: <code>{user['user_id']}</code>\n"
        f"┃ 💰 <b>PVP баланс:</b> {user['balance']} 🪙\n"
        f"┃ 🤖 <b>С ботом:</b> {bbot} 🤖\n"
        f"┃ 🃏 <b>Блэкджек:</b> {bj_bal} 🪙\n"
        f"┃ 🎮 <b>Сыграно игр:</b> {user['games_played']}\n"
        f"┃ 🏆 <b>Побед:</b> {user['wins']}\n"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="deposit"),
             InlineKeyboardButton(text="💸 Вывести средства", callback_data="withdraw")]
        ]
    )
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "deposit")
async def cb_deposit(call: CallbackQuery, state: FSMContext):
    if call.message.chat.type != "private":
        await call.answer("ℹ️ Для пополнения баланса перейдите в личные сообщения с ботом.", show_alert=True)
        bot_username = (await get_bot().me()).username
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Перейти в бота", url=f"https://t.me/{bot_username}")]
            ]
        )
        await call.message.answer(
            f"💳 {call.from_user.first_name}, для пополнения баланса перейдите в личные сообщения с ботом:",
            reply_markup=markup,
        )
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="100 🪙", callback_data="deposit_100"),
         InlineKeyboardButton(text="500 🪙", callback_data="deposit_500"),
         InlineKeyboardButton(text="1000 🪙", callback_data="deposit_1000")],
        [InlineKeyboardButton(text="5000 🪙", callback_data="deposit_5000"),
         InlineKeyboardButton(text="✏️ Другая", callback_data="deposit_custom")],
    ])
    await call.message.edit_text("💳 <b>Пополнение баланса</b>\n\nВыберите сумму:", parse_mode="HTML", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("deposit_"))
async def cb_deposit_preset(call: CallbackQuery, state: FSMContext):
    amount_str = call.data.split("_", 1)[1]
    if amount_str == "custom":
        await call.message.edit_text("💰 Введите сумму пополнения (от 100 до 10000 монет):")
        await state.set_state(DepositState.waiting_for_amount)
        await call.answer()
        return

    try:
        amount = int(amount_str)
    except ValueError:
        await call.answer("❌ Некорректная сумма!", show_alert=True)
        return

    await _submit_deposit_request(call.from_user.id, amount, call.message)
    await call.answer()


async def _submit_deposit_request(user_id: int, amount: int, msg: Message):
    if not (100 <= amount <= 10000):
        await msg.edit_text("❌ Сумма должна быть от 100 до 10000 монет.")
        return
    conn = await get_db()
    deposit_id = None
    try:
        cursor = await conn.execute(
            "SELECT id FROM deposit_requests WHERE user_id = ? AND status = 'pending'",
            (user_id,),
        )
        existing = await cursor.fetchone()
        if existing:
            await msg.edit_text("❌ У вас уже есть активный запрос на пополнение!")
            return
        cursor = await conn.execute(
            "INSERT INTO deposit_requests (user_id, amount, created) VALUES (?, ?, ?)",
            (user_id, amount, datetime.now().isoformat()),
        )
        await conn.commit()
        deposit_id = cursor.lastrowid
    finally:
        await conn.close()
    if deposit_id:
        await send_admin_notification(user_id, amount, deposit_id)
        await msg.edit_text(f"✅ Запрос на <b>{amount}</b> монет отправлен администратору.\nОжидайте реквизитов для оплаты.", parse_mode="HTML")
    else:
        await msg.edit_text("❌ Ошибка при создании запроса.")


@router.message(DepositState.waiting_for_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
    except (ValueError, TypeError):
        await message.answer("❌ Введите целое число от 100 до 10000.")
        return
    await state.clear()
    await _submit_deposit_request(message.from_user.id, amount, message)


async def send_admin_notification(user_id: int, amount: int, deposit_id: int):
    try:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="💳 Отправить реквизиты", callback_data=f"provide_{deposit_id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{deposit_id}"),
                ]
            ]
        )
        username = await get_username(user_id)
        await get_bot().send_message(
            ADMIN_ID,
            f"🆕 Запрос на пополнение\n\n"
            f"👤 Пользователь: {username}\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"💵 Сумма: {amount} монет",
            reply_markup=markup,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления админу: {e}")


@router.callback_query(F.data.startswith("provide_"))
async def cb_provide_details(call: CallbackQuery, state: FSMContext):
    if not await has_perm(call.from_user.id, "approve_deposits"):
        await call.answer("❌ Доступ запрещён!", show_alert=True)
        return

    deposit_id = int(call.data.split("_", 1)[1])
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, amount FROM deposit_requests WHERE id = ? AND status = 'pending'",
            (deposit_id,),
        )
        row = await cursor.fetchone()
        if not row:
            await call.answer("❌ Запрос уже обработан.", show_alert=True)
            return
    finally:
        await conn.close()

    await state.set_state(PaymentProvideState.waiting_for_details)
    await state.update_data(deposit_id=deposit_id, user_id=row["user_id"], amount=row["amount"])
    await call.message.edit_text(
        f"💳 Введите реквизиты для оплаты (одним сообщением):\n\n"
        f"Пример:\n"
        f"Номер карты: 1234 5678 9012 3456\n"
        f"Банк: СберБанк\n"
        f"Тип: MasterCard\n"
        f"Получатель: Иван И.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_provide")]
        ])
    )
    await call.answer()


@router.callback_query(F.data == "cancel_provide")
async def cb_cancel_provide(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ <b>Ввод реквизитов отменён.</b>", parse_mode="HTML")
    await call.answer()


@router.message(PaymentProvideState.waiting_for_details)
async def process_payment_details(message: Message, state: FSMContext):
    data = await state.get_data()
    deposit_id = data["deposit_id"]
    user_id = data["user_id"]
    amount = data["amount"]
    details = message.text.strip()

    if len(details) > 500:
        await message.answer("❌ Слишком много текста. Максимум 500 символов.")
        return

    conn = await get_db()
    try:
        await conn.execute(
            "UPDATE deposit_requests SET payment_details = ?, status = 'payment_sent' WHERE id = ? AND status = 'pending'",
            (details, deposit_id),
        )
        await conn.commit()
    finally:
        await conn.close()

    await state.clear()

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{deposit_id}"),
         InlineKeyboardButton(text="❌ Отмена", callback_data=f"reject_{deposit_id}")]
    ])
    await get_bot().send_message(
        user_id,
        f"💰 Пополнение на <b>{amount}</b> монет\n\n"
        f"📋 <b>Реквизиты для оплаты:</b>\n{details}\n\n"
        f"После перевода нажмите «Я оплатил».",
        parse_mode="HTML",
        reply_markup=markup,
    )

    await message.answer(f"✅ Реквизиты отправлены пользователю (ID: <code>{user_id}</code>).", parse_mode="HTML")
    try:
        await get_bot().delete_message(message.chat.id, message.message_id)
    except:
        pass


@router.callback_query(F.data.startswith("paid_"))
async def cb_user_paid(call: CallbackQuery):
    deposit_id = int(call.data.split("_", 1)[1])
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, amount FROM deposit_requests WHERE id = ? AND status = 'payment_sent'",
            (deposit_id,),
        )
        row = await cursor.fetchone()
        if not row:
            await call.answer("❌ Запрос уже обработан.", show_alert=True)
            return

        await conn.execute(
            "UPDATE deposit_requests SET status = 'paid' WHERE id = ?",
            (deposit_id,),
        )
        await conn.commit()
    finally:
        await conn.close()

    approve_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_{deposit_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{deposit_id}")]
    ])
    username = await get_username(row["user_id"])
    await get_bot().send_message(
        ADMIN_ID,
        f"👤 Пользователь: {username}\n"
        f"🆔 ID: <code>{row['user_id']}</code>\n"
        f"💵 Сумма: {row['amount']} монет\n\n"
        f"✅ Пользователь подтвердил оплату.\n"
        f"Проверьте свой счёт и подтвердите.",
        reply_markup=approve_markup,
        parse_mode="HTML",
    )

    await call.message.edit_text("✅ Оплата подтверждена. Ожидайте проверки администратором.")
    await call.answer()


@router.callback_query(F.data.startswith("approve_"))
async def cb_approve(call: CallbackQuery):
    if not await has_perm(call.from_user.id, "approve_deposits"):
        await call.answer("❌ Доступ запрещён!", show_alert=True)
        return

    deposit_id = int(call.data.split("_", 1)[1])
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, amount FROM deposit_requests WHERE id = ? AND status = 'paid'",
            (deposit_id,),
        )
        row = await cursor.fetchone()
        if not row:
            await call.answer("❌ Запрос уже обработан.", show_alert=True)
            return

        user_id = row["user_id"]
        amount = row["amount"]
        await update_balance(user_id, amount, "deposit")
        await conn.execute(
            "UPDATE deposit_requests SET status = 'approved' WHERE id = ?",
            (deposit_id,),
        )
        await conn.commit()

        await get_bot().send_message(user_id, f"✅ Ваш баланс пополнен на {amount} монет!")
    finally:
        await conn.close()

    await call.answer("✅ Подтверждено!")
    try:
        await get_bot().delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass


@router.callback_query(F.data.startswith("reject_"))
async def cb_reject(call: CallbackQuery):
    if not await has_perm(call.from_user.id, "approve_deposits"):
        await call.answer("❌ Доступ запрещён!", show_alert=True)
        return

    deposit_id = int(call.data.split("_", 1)[1])
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, amount, status FROM deposit_requests WHERE id = ?",
            (deposit_id,),
        )
        row = await cursor.fetchone()
        if not row or row["status"] in ("approved", "rejected"):
            await call.answer("❌ Запрос уже обработан.", show_alert=True)
            return

        await conn.execute(
            "UPDATE deposit_requests SET status = 'rejected' WHERE id = ?",
            (deposit_id,),
        )
        await conn.commit()

        await get_bot().send_message(row["user_id"], "❌ Ваш запрос на пополнение был отклонён.")
    finally:
        await conn.close()

    await call.answer("❌ Отклонено")
    try:
        await get_bot().delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass


@router.message(Command("одобрить"))
async def cmd_approve_deposit(message: Message):
    if not await has_perm(message.from_user.id, "approve_deposits"):
        await message.reply("❌ Доступ запрещён!")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("❌ Формат: <code>/одобрить ID_запроса</code>")
        return

    try:
        deposit_id = int(parts[1])
    except ValueError:
        await message.reply("❌ Укажите числовой ID запроса.")
        return

    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, amount FROM deposit_requests WHERE id = ? AND status = 'paid'",
            (deposit_id,),
        )
        row = await cursor.fetchone()
        if not row:
            await message.reply("❌ Запрос не найден или ещё не оплачен пользователем.")
            return

        user_id = row["user_id"]
        amount = row["amount"]
        await update_balance(user_id, amount, "deposit")
        await conn.execute(
            "UPDATE deposit_requests SET status = 'approved' WHERE id = ?",
            (deposit_id,),
        )
        await conn.commit()
        await get_bot().send_message(user_id, f"✅ Ваш баланс пополнен на {amount} монет!")
        await message.reply(f"✅ Запрос #{deposit_id} одобрен. Баланс пополнен на {amount} монет.")
    finally:
        await conn.close()


@router.message(Command("пополнить"))
async def cmd_admin_add_balance(message: Message):
    if not await has_perm(message.from_user.id, "add_balance"):
        await message.reply("❌ Доступ запрещён!")
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.reply("❌ Формат: <code>/пополнить user_id сумма</code>")
        return

    try:
        user_id = int(parts[1])
        amount = int(parts[2])
    except (ValueError, IndexError):
        await message.reply("❌ Формат: <code>/пополнить user_id сумма</code>")
        return

    await update_balance(user_id, amount, "admin_add")
    await message.reply(f"✅ Баланс пользователя <code>{user_id}</code> пополнен на <b>{amount}</b> монет!")
    try:
        admin_name = message.from_user.username or "Администратор"
        await get_bot().send_message(
            user_id,
            f"<b>💰 Баланс пополнен!</b>\n\n"
            f"┃ Сумма: +{amount} 🪙\n"
            f"┃ Пополнил: @{admin_name}\n\n"
            f"🎉 Приятной игры!",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.message(Command("выводы"))
async def cmd_withdrawals(message: Message):
    if not await has_perm(message.from_user.id, "approve_withdrawals"):
        await message.reply("❌ Доступ запрещён!")
        return
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT * FROM withdraw_requests WHERE status = 'pending' ORDER BY created"
        )
        pending = await cursor.fetchall()
    finally:
        await conn.close()

    if not pending:
        await message.reply("💸 Нет ожидающих запросов на вывод.")
        return

    text = "<b>💸 Ожидающие запросы на вывод:</b>\n\n"
    for req in pending[:10]:
        username = await get_username(req["user_id"])
        text += (
            f"┃ <b>#{req['id']}</b>\n"
            f"┃ 👤 {username}\n"
            f"┃ 🆔 <code>{req['user_id']}</code>\n"
            f"┃ 💵 {req['amount']} монет\n"
            f"┃ 💳 {req['card_details'][:40]}{'...' if len(req['card_details']) > 40 else ''}\n"
            f"┃ 📅 {req['created']}\n\n"
        )
    if len(pending) > 10:
        text += f"┃ <i>...и ещё {len(pending) - 10} запросов</i>"

    await message.reply(text, parse_mode="HTML")


@router.callback_query(F.data == "withdraw")
async def cb_withdraw(call: CallbackQuery, state: FSMContext):
    if call.message.chat.type != "private":
        await call.answer("ℹ️ Для вывода средств перейдите в личные сообщения с ботом.", show_alert=True)
        bot_username = (await get_bot().me()).username
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Перейти в бота", url=f"https://t.me/{bot_username}")]
            ]
        )
        await call.message.answer(
            f"💸 {call.from_user.first_name}, для вывода средств перейдите в личные сообщения с ботом:",
            reply_markup=markup,
        )
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="100 🪙", callback_data="withdraw_100"),
         InlineKeyboardButton(text="500 🪙", callback_data="withdraw_500"),
         InlineKeyboardButton(text="1000 🪙", callback_data="withdraw_1000")],
        [InlineKeyboardButton(text="5000 🪙", callback_data="withdraw_5000"),
         InlineKeyboardButton(text="✏️ Другая", callback_data="withdraw_custom")],
    ])
    await call.message.edit_text("💸 <b>Вывод средств</b>\n\nВыберите сумму:", parse_mode="HTML", reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith("withdraw_"), ~F.data.startswith("withdraw_approve_"), ~F.data.startswith("withdraw_reject_"))
async def cb_withdraw_preset(call: CallbackQuery, state: FSMContext):
    amount_str = call.data.split("_", 1)[1]
    if amount_str == "custom":
        await call.message.edit_text("💰 Введите сумму вывода (от 100 до 10000 монет):")
        await state.set_state(WithdrawState.waiting_for_card)
        await state.update_data(amount=None)
        await call.answer()
        return

    try:
        amount = int(amount_str)
    except ValueError:
        await call.answer("❌ Некорректная сумма!", show_alert=True)
        return

    await state.update_data(amount=amount)
    await call.message.edit_text(
        f"💳 Введите реквизиты карты для вывода <b>{amount}</b> монет:\n\n"
        f"Пример:\n"
        f"Номер карты: 1234 5678 9012 3456\n"
        f"Банк: СберБанк\n"
        f"Получатель: Иван И.",
        parse_mode="HTML"
    )
    await state.set_state(WithdrawState.waiting_for_card)
    await call.answer()


@router.message(WithdrawState.waiting_for_card)
async def process_withdraw_card(message: Message, state: FSMContext):
    data = await state.get_data()
    amount = data.get("amount")
    if amount is None:
        try:
            amount = int(message.text.strip())
        except (ValueError, TypeError):
            await message.answer("❌ Введите целое число от 100 до 10000.")
            return
        if not (100 <= amount <= 10000):
            await message.answer("❌ Сумма должна быть от 100 до 10000 монет.")
            return
        await state.update_data(amount=amount)
        await message.answer(
            f"💳 Введите реквизиты карты для вывода <b>{amount}</b> монет:\n\n"
            f"Пример:\nНомер карты: 1234 5678 9012 3456\nБанк: СберБанк\nПолучатель: Иван И.",
            parse_mode="HTML"
        )
        return

    card_details = message.text.strip()
    if len(card_details) > 500:
        await message.answer("❌ Слишком много текста. Максимум 500 символов.")
        return

    user = await get_user(message.from_user.id)
    if not user or user["balance"] < amount:
        await message.answer("❌ Недостаточно средств на балансе!")
        await state.clear()
        return

    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT id FROM withdraw_requests WHERE user_id = ? AND status = 'pending'",
            (message.from_user.id,),
        )
        if await cursor.fetchone():
            await message.answer("❌ У вас уже есть активный запрос на вывод!")
            await state.clear()
            return

        cursor = await conn.execute(
            "INSERT INTO withdraw_requests (user_id, amount, card_details, created) VALUES (?, ?, ?, ?)",
            (message.from_user.id, amount, card_details, datetime.now().isoformat()),
        )
        await conn.commit()
        withdraw_id = cursor.lastrowid
    finally:
        await conn.close()

    await state.clear()

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"withdraw_approve_{withdraw_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"withdraw_reject_{withdraw_id}")]
    ])
    username = await get_username(message.from_user.id)
    admins = await get_users_with_perm("approve_withdrawals")
    for admin_id in admins:
        try:
            await get_bot().send_message(
                admin_id,
                f"🆕 Запрос на вывод средств\n\n"
                f"👤 Пользователь: {username}\n"
                f"🆔 ID: <code>{message.from_user.id}</code>\n"
                f"💵 Сумма: {amount} монет\n"
                f"💳 Карта: {card_details}",
                reply_markup=markup,
                parse_mode="HTML",
            )
        except Exception:
            pass

    await message.answer(
        f"✅ Запрос на вывод <b>{amount}</b> монет отправлен администратору.\n"
        f"Ожидайте подтверждения.",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("withdraw_approve_"))
async def cb_withdraw_approve(call: CallbackQuery):
    if not await has_perm(call.from_user.id, "approve_withdrawals"):
        await call.answer("❌ Доступ запрещён!", show_alert=True)
        return

    withdraw_id = int(call.data.split("_", 2)[2])
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id, amount FROM withdraw_requests WHERE id = ? AND status = 'pending'",
            (withdraw_id,),
        )
        row = await cursor.fetchone()
        if not row:
            await call.answer("❌ Запрос уже обработан.", show_alert=True)
            return

        user_id = row["user_id"]
        amount = row["amount"]

        cursor2 = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user = await cursor2.fetchone()
        if not user or user["balance"] < amount:
            await call.answer("❌ Недостаточно средств у пользователя!", show_alert=True)
            return

        await conn.execute(
            "UPDATE withdraw_requests SET status = 'approved' WHERE id = ?",
            (withdraw_id,),
        )
        await conn.commit()
    finally:
        await conn.close()

    await update_balance(user_id, -amount, "withdraw")

    await get_bot().send_message(
        user_id,
        f"✅ Ваш запрос на вывод <b>{amount}</b> монет одобрен!\n"
        f"Средства отправлены на указанную карту.",
        parse_mode="HTML"
    )

    await call.answer("✅ Вывод подтверждён!")
    try:
        await get_bot().delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass


@router.callback_query(F.data.startswith("withdraw_reject_"))
async def cb_withdraw_reject(call: CallbackQuery):
    if not await has_perm(call.from_user.id, "approve_withdrawals"):
        await call.answer("❌ Доступ запрещён!", show_alert=True)
        return

    withdraw_id = int(call.data.split("_", 2)[2])
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT user_id FROM withdraw_requests WHERE id = ? AND status = 'pending'",
            (withdraw_id,),
        )
        row = await cursor.fetchone()
        if not row:
            await call.answer("❌ Запрос уже обработан.", show_alert=True)
            return

        await conn.execute(
            "UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?",
            (withdraw_id,),
        )
        await conn.commit()

        await get_bot().send_message(row["user_id"], "❌ Ваш запрос на вывод был отклонён.")
    finally:
        await conn.close()

    await call.answer("❌ Отклонено")
    try:
        await get_bot().delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass


@router.message(Command("promo"))
async def cmd_activate_promo(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("❌ Укажите промокод. Пример: <code>/promo WELCOME100</code>", parse_mode="HTML")
        return

    code = parts[1].strip().upper()
    user_id = message.from_user.id

    conn = await get_db()
    try:
        cursor = await conn.execute("SELECT amount FROM promocodes WHERE code = ?", (code,))
        promo = await cursor.fetchone()
        if not promo:
            await message.reply("❌ Промокод не найден.")
            return

        amount = promo["amount"]

        cursor = await conn.execute(
            "SELECT 1 FROM promo_activations WHERE code = ? AND user_id = ?",
            (code, user_id),
        )
        if await cursor.fetchone():
            await message.reply("❌ Вы уже активировали этот промокод.")
            return
    finally:
        await conn.close()

    await update_balance(user_id, amount, "promo")

    conn = await get_db()
    try:
        await conn.execute(
            "INSERT INTO promo_activations (code, user_id, activated_at) VALUES (?, ?, ?)",
            (code, user_id, datetime.now().isoformat()),
        )
        await conn.commit()
    finally:
        await conn.close()

    await message.reply(f"🎉 <b>Промокод активирован!</b>\n💰 +{amount} 🪙 на ваш баланс!", parse_mode="HTML")


@router.message(Command("createpromo"))
async def cmd_create_promo(message: Message):
    if not is_owner(message.from_user.id) and not await has_perm(message.from_user.id, "create_promos"):
        await message.reply("❌ Только разработчик или админ с правом create_promos может создавать промокоды!")
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("❌ Формат: <code>/createpromo КОД сумма</code>\nПример: <code>/createpromo WELCOME 500</code>")
        return

    code = parts[1].strip().upper()
    try:
        amount = int(parts[2])
    except ValueError:
        await message.reply("❌ Сумма должна быть числом.")
        return

    if amount < 1:
        await message.reply("❌ Сумма должна быть больше 0.")
        return

    conn = await get_db()
    try:
        cursor = await conn.execute("SELECT 1 FROM promocodes WHERE code = ?", (code,))
        if await cursor.fetchone():
            await message.reply(f"❌ Промокод <code>{code}</code> уже существует.")
            return
        await conn.execute(
            "INSERT INTO promocodes (code, amount, created_by, created_at) VALUES (?, ?, ?, ?)",
            (code, amount, message.from_user.id, datetime.now().isoformat()),
        )
        await conn.commit()
    finally:
        await conn.close()

    await message.reply(f"✅ Промокод <code>{code}</code> на <b>{amount}</b> монет создан!")


@router.message(Command("deletepromo"))
async def cmd_delete_promo(message: Message):
    if not is_owner(message.from_user.id) and not await has_perm(message.from_user.id, "create_promos"):
        await message.reply("❌ Только разработчик может удалять промокоды!")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("❌ Формат: <code>/deletepromo КОД</code>")
        return

    code = parts[1].strip().upper()
    conn = await get_db()
    try:
        await conn.execute("DELETE FROM promocodes WHERE code = ?", (code,))
        await conn.commit()
    finally:
        await conn.close()

    await message.reply(f"✅ Промокод <code>{code}</code> удалён.")


@router.message(Command("promo_list"))
async def cmd_promo_list(message: Message):
    if not is_owner(message.from_user.id) and not await has_perm(message.from_user.id, "create_promos"):
        await message.reply("❌ Только разработчик может просматривать промокоды!")
        return

    conn = await get_db()
    try:
        cursor = await conn.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
        promos = await cursor.fetchall()
    finally:
        await conn.close()

    if not promos:
        await message.reply("📋 Нет созданных промокодов.")
        return

    lines = ["<b>📋 Промокоды:</b>\n"]
    for p in promos:
        conn2 = await get_db()
        try:
            cur2 = await conn2.execute(
                "SELECT COUNT(*) as cnt FROM promo_activations WHERE code = ?", (p["code"],)
            )
            cnt_row = await cur2.fetchone()
            activations = cnt_row["cnt"] if cnt_row else 0
        finally:
            await conn2.close()
        lines.append(f"┃ <code>{p['code']}</code> — {p['amount']} 🪙  |  активаций: {activations}")
    await message.reply("\n".join(lines), parse_mode="HTML")
