import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
from bs4 import BeautifulSoup
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "9048554432:AAGLng2a3paZaj_X7kiuwN0FAhdDw71214o"
bot = telebot.TeleBot(BOT_TOKEN)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Scraper Bot is running!")

def run_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

@bot.message_handler(commands=['start', 'new'])
def get_latest_movies(message):
    msg = bot.reply_to(message, "در حال دریافت لیست جدیدترین فیلم‌ها از سایت...")
    try:
        response = requests.get("https://www.uptvs.com/", headers=HEADERS, timeout=15)
        if response.status_code != 200:
            bot.edit_message_text(f"خطا در اتصال به سایت (کد وضعیت: {response.status_code}). احتمالاً آی‌پی سرور مسدود است.", message.chat.id, msg.message_id)
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        markup = InlineKeyboardMarkup()
        
        # پیدا کردن لینک پست‌ها (تگ‌ها بسته به قالب سایت تنظیم می‌شوند)
        articles = soup.find_all('article', limit=8)
        count = 0
        for article in articles:
            link_tag = article.find('a', href=True)
            if link_tag and link_tag.get('title'):
                title = link_tag.get('title').strip()
                url = link_tag['href']
                # ارسال لینک صفحه به عنوان داده دکمه
                markup.add(InlineKeyboardButton(text=title[:40], callback_data=f"dl|{url[:55]}"))
                count += 1

        if count == 0:
            bot.edit_message_text("فیلمی پیدا نشد. نیاز به تنظیم دقیق‌تر تگ‌های HTML سایت است.", message.chat.id, msg.message_id)
        else:
            bot.edit_message_text("جدیدترین فیلم‌های سایت (برای دریافت لینک کلیک کنید):", message.chat.id, msg.message_id, reply_markup=markup)

    except Exception as e:
        bot.edit_message_text(f"خطا در ارتباط با سایت:\n{str(e)[:100]}", message.chat.id, msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dl|"))
def fetch_download_links(call):
    page_url = call.data.split("|", 1)[1]
    bot.answer_callback_query(call.id, "در حال استخراج لینک‌های دانلود...")
    
    try:
        res = requests.get(page_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # پیدا کردن تمام لینک‌هایی که پسوند ویدیو دارند (mp4 یا mkv)
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.endswith(('.mkv', '.mp4')):
                quality_text = a.get_text(strip=True) or "لینک دانلود"
                links.append(f"🎬 <a href='{href}'>{quality_text}</a>")

        if links:
            result_text = "لینک‌های مستقیم دانلود:\n\n" + "\n".join(links[:6])
            bot.send_message(call.message.chat.id, result_text, parse_mode="HTML", disable_web_page_preview=True)
        else:
            bot.send_message(call.message.chat.id, f"لینک مستقیمی در صفحه پیدا نشد. صفحه فیلم:\n{page_url}")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"خطا در دریافت صفحه فیلم: {str(e)[:100]}")

if __name__ == "__main__":
    threading.Thread(target=run_health_server, daemon=True).start()
    bot.infinity_polling()
