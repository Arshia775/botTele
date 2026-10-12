import os
import random
import logging

import requests
from bs4 import BeautifulSoup
import telebot
from telebot import types

# ── لاگ ───────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# 🔐 توکن ربات
# ---------------------------------------------------------------
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ توکن ربات تنظیم نشده است!")

bot = telebot.TeleBot(TOKEN)

# ── ثابت‌ها ───────────────────────────────────────────────
URL = "https://arzdigital.com/currencies/united-states-dollar/"

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
LATIN_DIGITS = "0123456789"
DIGIT_MAP = str.maketrans(PERSIAN_DIGITS, LATIN_DIGITS)

# ── ذخیره وضعیت کاربران ───────────────────────────────────
# ساختار: { user_id: {"state": "captcha" | "menu", "answer": int} }
user_states: dict[int, dict] = {}


# ── تبدیل اعداد فارسی به لاتین ────────────────────────────
def persian_to_latin(text: str) -> str:
    """تبدیل ارقام فارسی به لاتین"""
    return text.translate(DIGIT_MAP)


# ── دریافت قیمت دلار از ارزدیجیتال ────────────────────────
def get_dollar_price() -> str | None:
    """
    استخراج قیمت لحظه‌ای دلار به تومان از سایت ارزدیجیتال
    تگ هدف:
        <span class="arz-irt-price" dir="rtl">
            <span>۲۶۳,۲۰۰</span>
            <span class="arz-irt-symbol"></span>
        </span>
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    }

    try:
        response = requests.get(URL, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = "utf-8"

        soup = BeautifulSoup(response.text, "html.parser")

        # سلکتور اصلی
        price_tag = soup.select_one("span.arz-irt-price > span:first-child")

        # سلکتور جایگزین در صورت تغییر ساختار
        if not price_tag:
            price_tag = soup.select_one(
                ".arz-coin-page-data__coin-toman-price span.arz-irt-price span"
            )

        if not price_tag:
            return None

        raw_price = price_tag.get_text(strip=True)      # مثال: ۲۶۳,۲۰۰
        latin_price = persian_to_latin(raw_price)       # مثال: 263,200
        numeric_price = latin_price.replace(",", "")    # مثال: 263200

        return numeric_price

    except requests.RequestException as e:
        logger.error(f"خطا در دریافت قیمت: {e}")
        return None


# ── دستور /start و کپچا ───────────────────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    """ارسال کپچای ریاضی ساده"""
    a = random.randint(1, 15)
    b = random.randint(1, 15)
    answer = a + b

    user_states[message.chat.id] = {"state": "captcha", "answer": answer}

    bot.send_message(
        message.chat.id,
        f"🤖 برای اطمینان از اینکه ربات نیستید، لطفاً پاسخ عبارت زیر را ارسال کنید:\n\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"   {a}  +  {b}  =  ?\n"
        f"➖➖➖➖➖➖➖➖\n\n"
        f"فقط عدد پاسخ را بفرستید.",
        reply_markup=types.ReplyKeyboardRemove(),
    )


# ── دستور /price (قیمت لحظه‌ای) ────────────────────────────
@bot.message_handler(commands=["price"])
def cmd_price(message: types.Message):
    state = user_states.get(message.chat.id, {}).get("state")

    if state != "menu":
        bot.send_message(
            message.chat.id,
            "⚠️ ابتدا باید کپچا را حل کنید.\nبرای شروع /start را بزنید.",
        )
        return

    bot.send_message(message.chat.id, "⏳ در حال دریافت قیمت از ارزدیجیتال...")

    price = get_dollar_price()

    if price is None:
        bot.send_message(
            message.chat.id,
            "❌ متأسفانه در دریافت قیمت خطایی رخ داد.\n"
            "لطفاً چند لحظه بعد دوباره تلاش کنید.",
        )
        return

    formatted = f"{int(price):,}"

    bot.send_message(
        message.chat.id,
        f"💵 <b>قیمت لحظه‌ای دلار (بازار آزاد)</b>\n\n"
        f"💰 <code>{formatted}</code> تومان\n\n"
        f"🔗 منبع: arzdigital.com",
        parse_mode="HTML",
    )


# ── دستور /cancel ─────────────────────────────────────────
@bot.message_handler(commands=["cancel"])
def cmd_cancel(message: types.Message):
    user_states.pop(message.chat.id, None)
    bot.send_message(
        message.chat.id,
        "مکالمه لغو شد. برای شروع مجدد /start را بزنید.",
        reply_markup=types.ReplyKeyboardRemove(),
    )


# ── هندلر عمومی متن (مدیریت کپچا) ─────────────────────────
@bot.message_handler(
    func=lambda msg: msg.chat.id in user_states
    and user_states[msg.chat.id].get("state") == "captcha",
    content_types=["text"],
)
def handle_captcha(message: types.Message):
    text = message.text.strip()

    if not text.isdigit():
        bot.send_message(message.chat.id, "⚠️ لطفاً فقط عدد ارسال کنید.")
        return

    correct = user_states[message.chat.id].get("answer")

    if int(text) == correct:
        user_states[message.chat.id] = {"state": "menu"}
        bot.send_message(
            message.chat.id,
            "✅ تایید شد! خوش آمدید.\n\n"
            "برای دریافت قیمت لحظه‌ای دلار دستور /price را ارسال کنید.",
        )
    else:
        user_states.pop(message.chat.id, None)
        bot.send_message(
            message.chat.id,
            "❌ پاسخ اشتباه است. لطفاً دوباره تلاش کنید.\n"
            "برای دریافت کپچای جدید /start را بزنید.",
        )


# ── هندلر پیش‌فرض پیام‌های متفرقه ──────────────────────────
@bot.message_handler(content_types=["text"])
def fallback(message: types.Message):
    state = user_states.get(message.chat.id, {}).get("state")

    if state == "menu":
        bot.send_message(
            message.chat.id,
            "برای دریافت قیمت لحظه‌ای دلار دستور /price را ارسال کنید.",
        )
    else:
        bot.send_message(
            message.chat.id,
            "برای شروع /start را بزنید.",
        )


# ── اجرا ──────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("🤖 ربات در حال اجراست...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
