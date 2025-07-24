from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from config import BOT_TOKEN, ADMIN_PASSWORD, ADMINS_FILE, SUB_FILES

ACTIVE_REQUESTS = {}
WAITING_ADMIN_PASSWORD = set()

# ---- Работа с администраторами ----
def load_admins():
    try:
        with open(ADMINS_FILE, "r") as f:
            return [int(line.strip()) for line in f if line.strip()]
    except FileNotFoundError:
        return []

def save_admin(user_id):
    admins = set(load_admins())
    admins.add(user_id)
    with open(ADMINS_FILE, "w") as f:
        for uid in admins:
            f.write(f"{uid}\n")

ADMINS = load_admins()

def is_admin(user_id):
    return user_id in ADMINS

# --- Меню ---
def get_reply_main_menu():
    keyboard = [
        ["Подписки", "Admin"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_sub_menu():
    keyboard = [
        [
            InlineKeyboardButton("Подписаться на 3т", callback_data="sub_3"),
            InlineKeyboardButton("Отписаться от 3т", callback_data="unsub_3"),
        ],
        [
            InlineKeyboardButton("Подписаться на 5т", callback_data="sub_5"),
            InlineKeyboardButton("Отписаться от 5т", callback_data="unsub_5"),
        ],
        [
            InlineKeyboardButton("Подписаться на 10т", callback_data="sub_10"),
            InlineKeyboardButton("Отписаться от 10т", callback_data="unsub_10"),
        ],
        [InlineKeyboardButton("Назад", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)

def load_subs(category):
    try:
        with open(SUB_FILES[category], "r") as f:
            return set(int(line.strip()) for line in f if line.strip())
    except FileNotFoundError:
        return set()

def save_subs(category, subs):
    with open(SUB_FILES[category], "w") as f:
        for user_id in subs:
            f.write(f"{user_id}\n")

def get_weight_category(weight):
    if weight <= 3:
        return "3"
    elif weight <= 5:
        return "5"
    elif weight <= 10:
        return "10"
    else:
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=get_reply_main_menu()
    )

async def reply_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.lower().strip()

    # --- Ввод пароля логиста (приоритетно) ---
    if user_id in WAITING_ADMIN_PASSWORD:
        WAITING_ADMIN_PASSWORD.remove(user_id)
        if text == ADMIN_PASSWORD:
            save_admin(user_id)
            ADMINS.clear()
            ADMINS.extend(load_admins())
            await update.message.reply_text(
                "Доступ администратора получен! Теперь вы можете отправлять заявки.",
                reply_markup=get_reply_main_menu()
            )
        else:
            await update.message.reply_text(
                "Неверный пароль. Попробуйте снова (нажмите Admin для повтора).",
                reply_markup=get_reply_main_menu()
            )
        return

    # --- Обычные действия меню ---
    if text == "подписки":
        await update.message.reply_text(
            "Меню подписки на категории:",
            reply_markup=get_sub_menu()
        )
    elif text == "admin":
        WAITING_ADMIN_PASSWORD.add(user_id)
        await update.message.reply_text(
            "Введите пароль администратора:",
            reply_markup=get_reply_main_menu()
        )
    else:
        await update.message.reply_text(
            "Пожалуйста, отвечайте на заявку нажимая ""ответить"" или создавайте заявку послав скриншот маршрута если Вы логист",
            reply_markup=get_reply_main_menu()
        )

async def sub_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Обрабатываем кнопку "Назад"
    if data == "back_main":
        await query.edit_message_text(
            "Выберите действие:",
            reply_markup=get_reply_main_menu()
        )
        return

    if "_" not in data:
        return
    action, category = query.data.split("_")
    user_id = query.from_user.id

    subs = load_subs(category)
    if action == "sub":
        if user_id in subs:
            await query.edit_message_text(f"Вы уже подписаны на {category}т.", reply_markup=get_sub_menu())
        else:
            subs.add(user_id)
            save_subs(category, subs)
            await query.edit_message_text(f"Вы подписаны на {category}т.", reply_markup=get_sub_menu())
    elif action == "unsub":
        if user_id not in subs:
            await query.edit_message_text(f"Вы не были подписаны на {category}т.", reply_markup=get_sub_menu())
        else:
            subs.remove(user_id)
            save_subs(category, subs)
            await query.edit_message_text(f"Вы отписаны от {category}т.", reply_markup=get_sub_menu())
    elif action == "back":
        await query.edit_message_text(
            "Выберите действие:",
            reply_markup=get_reply_main_menu()
        )

async def new_route(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("У вас нет прав для отправки заявок.")
        return

    if update.message.photo and update.message.caption:
        try:
            weight = float(update.message.caption.split()[0].replace(",", "."))
        except Exception:
            await update.message.reply_text("Укажите вес первым числом в подписи к фото.")
            return

        category = get_weight_category(weight)
        if not category:
            await update.message.reply_text("Нет подходящей категории по весу.")
            return

        user_ids = load_subs(category)
        if not user_ids:
            await update.message.reply_text("Нет подписчиков для этой категории.")
            return

        caption_for_admin = f"Заявка:\nВес: {weight} т\nОписание: {update.message.caption}"
        caption_for_users = caption_for_admin + "\n\nОтветьте на это сообщение вашей ценой (ответить на сообщение)."

        sent_count = 0
        for uid in user_ids:
            try:
                sent = await context.bot.send_photo(
                    chat_id=uid,
                    photo=update.message.photo[-1].file_id,
                    caption=caption_for_users
                )
                ACTIVE_REQUESTS[sent.message_id] = (
                    update.message.from_user.id,
                    update.message.photo[-1].file_id,
                    caption_for_admin
                )
                sent_count += 1
            except Exception as e:
                print(f"Не удалось отправить пользователю {uid}: {e}")

        await update.message.reply_text(f"Заявка разослана {sent_count} подписчикам категории {category}т.")

async def offer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply = update.message.reply_to_message
    if reply is None:
        await update.message.reply_text("Ответ принимается только как reply на заявку.")
        return

    if reply.message_id not in ACTIVE_REQUESTS:
        await update.message.reply_text("Ответ принимается только на сообщения-заявки, разосланные ботом.")
        return

    admin_id, file_id, caption_for_admin = ACTIVE_REQUESTS[reply.message_id]
    sender = update.message.from_user
    price = update.message.text.strip()
    sender_name = f"@{sender.username}" if sender.username else sender.full_name

    msg_text = (
        f"Поступило предложение: {price}\n"
        f"От {sender_name}\n\n"
        f"Исходная заявка:"
    )

    await context.bot.send_photo(
        chat_id=admin_id,
        photo=file_id,
        caption=msg_text + "\n" + caption_for_admin
    )
    await update.message.reply_text("Ваше предложение отправлено логисту.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(sub_button))
    app.add_handler(MessageHandler(filters.PHOTO & filters.Caption(), new_route))
    app.add_handler(MessageHandler(filters.TEXT & filters.REPLY, offer_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_menu_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
