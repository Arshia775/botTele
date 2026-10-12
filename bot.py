import os
import telebot

# خواندن توکن از متغیرهای محیطی برای امنیت بالا
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("توکن ربات تلگرام تنظیم نشده است!")

bot = telebot.TeleBot(TOKEN)

# پاسخ به دستور /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_name = message.from_user.first_name
    welcome_text = (
        f"سلام {user_name} عزیز! 👋\n"
        "به ربات خوش آمدید. پیام شما دریافت شد!"
    )
    bot.reply_to(message, welcome_text)

# پاسخ به سایر پیام‌های متنی
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, "پیام شما دریافت شد. در حال حاضر فقط دستور /start فعال است.")

# اجرای مداوم دریافت پیام‌ها
if __name__ == "__main__":
    print("ربات با موفقیت روشن شد...")
    bot.infinity_polling()
