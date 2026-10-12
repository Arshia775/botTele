import os
import requests
import telebot
from telebot import types
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ---------------------------------------------------------------
# 🔐 توکن
# ---------------------------------------------------------------
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ توکن ربات تنظیم نشده است!")

bot = telebot.TeleBot(TOKEN)

BASE_URL = "https://gapfilm.ir"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
}

# ===============================================================
# 🕷️ تابع اصلی اسکرپینگ
# ===============================================================
def fetch_latest_content(limit: int = 6):
    """
    صفحه اصلی gapfilm.ir را دریافت و جدیدترین فیلم/سریال‌ها را استخراج می‌کند.
    خروجی: لیستی از دیکشنری‌ها با کلیدهای title, link, image, rating, type
    """
    try:
        resp = requests.get(BASE_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"⚠️ خطا در دریافت صفحه: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    results = []
    seen = set()  # جلوگیری از تکرار

    # -----------------------------------------------------------
    # 🎯 استخراج از اسلایدر اصلی (جدیدترین‌ها)
    # هر آیتم شامل <a href="/movie/..."> یا <a href="/serial/...">
    # -----------------------------------------------------------
    for a_tag in soup.select('a[href*="/movie/"], a[href*="/serial/"]'):
        href = a_tag.get("href", "")
        if not href or href in seen:
            continue

        # استخراج عنوان از alt تصویر یا تگ h3
        img = a_tag.find("img")
        title = ""
        image_url = ""

        if img:
            title = img.get("alt", "").strip()
            image_url = (
                img.get("src")
                or img.get("data-src")
                or ""
            )

        # اگر عنوان از alt نیامد، از h3 داخل لینک بخوان
        if not title:
            h3 = a_tag.find("h3")
            if h3:
                title = h3.get_text(strip=True)

        if not title:
            continue

        seen.add(href)

        # امتیاز IMDb (اختیاری)
        rating = ""
        rating_span = a_tag.find("span", class_=lambda c: c and "rait" in c)
        if rating_span:
            rating = rating_span.get_text(strip=True)

        # نوع محتوا (فیلم/سریال)
        content_type = "فیلم" if "/movie/" in href else "سریال"

        full_link = urljoin(BASE_URL, href)

        results.append({
            "title": title,
            "link": full_link,
            "image": image_url,
            "rating": rating,
            "type": content_type,
        })

        if len(results) >= limit:
            break

    # اگر هیچ نتیجه‌ای از اسلایدر نیامد، از کارت‌های اصلی استفاده کن
    if not results:
        results = _fallback_scrape(soup, limit)

    return results


def _fallback_scrape(soup, limit):
    """روش جایگزین: استخراج از کارت‌های بخش‌های اصلی."""
    results = []
    seen = set()

    # کارت‌های محتوایی که معمولاً در section های اصلی هستند
    for card in soup.select('div.next-1xa9zkv, div.next-1hygfzp, div.next-xdq8fq'):
        parent_a = card.find_parent("a", href=True)
        if not parent_a:
            continue

        href = parent_a["href"]
        if href in seen:
            continue
        seen.add(href)

        img = card.find("img")
        title = img.get("alt", "").strip() if img else ""
        image_url = ""
        if img:
            image_url = img.get("src") or img.get("data-src") or ""

        if not title:
            h3 = parent_a.find("h3")
            if h3:
                title = h3.get_text(strip=True)

        if not title:
            continue

        rating = ""
        rating_span = parent_a.find("span", class_=lambda c: c and "rait" in c)
        if rating_span:
            rating = rating_span.get_text(strip=True)

        content_type = "فیلم" if "/movie/" in href else "سریال"
        full_link = urljoin(BASE_URL, href)

        results.append({
            "title": title,
            "link": full_link,
            "image": image_url,
            "rating": rating,
            "type": content_type,
        })

        if len(results) >= limit:
            break

    return results


# ===============================================================
# 📤 ارسال نتایج به تلگرام
# ===============================================================
def send_content_list(chat_id, items, header="🎬 **جدیدترین‌های گپ فیلم**"):
    """لیست آیتم‌ها را با تصویر و دکمه شیشه‌ای ارسال می‌کند."""
    if not items:
        bot.send_message(
            chat_id,
            "😔 متأسفانه در حال حاضر محتوایی از سایت دریافت نشد.\n"
            "لطفاً بعداً دوباره امتحان کنید.",
        )
        return

    bot.send_message(chat_id, header, parse_mode="Markdown")

    for item in items:
        caption = (
            f"🎬 **{item['title']}**\n"
            f"📌 نوع: {item['type']}\n"
        )
        if item["rating"]:
            caption += f"⭐ امتیاز IMDb: {item['rating']}\n"

        # دکمه شیشه‌ای برای مشاهده در سایت
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                text="▶️ مشاهده در گپ فیلم",
                url=item["link"],
            )
        )

        # اگر تصویر داشت، با عکس بفرست؛ وگرنه فقط متن + دکمه
        if item["image"] and item["image"].startswith("http"):
            try:
                bot.send_photo(
                    chat_id,
                    photo=item["image"],
                    caption=caption,
                    reply_markup=kb,
                    parse_mode="Markdown",
                )
            except Exception as e:
                print(f"⚠️ خطا در ارسال عکس {item['title']}: {e}")
                bot.send_message(
                    chat_id,
                    caption,
                    reply_markup=kb,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
        else:
            bot.send_message(
                chat_id,
                caption,
                reply_markup=kb,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )


# ===============================================================
# 🎛️ منوی اصلی ربات
# ===============================================================
def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("🎬 جدیدترین فیلم‌ها", callback_data="new_movies"),
        types.InlineKeyboardButton("📺 جدیدترین سریال‌ها", callback_data="new_series"),
    )
    kb.row(
        types.InlineKeyboardButton("🔥 برترین‌ها", callback_data="top_rated"),
        types.InlineKeyboardButton("🔍 جستجو در سایت", url=f"{BASE_URL}/search/"),
    )
    kb.row(
        types.InlineKeyboardButton("📥 اپلیکیشن‌ها", url=f"{BASE_URL}/faq/7/"),
        types.InlineKeyboardButton("💳 خرید اشتراک", url=f"{BASE_URL}/landing/subscription/"),
    )
    return kb


# ===============================================================
# 🚀 دستور /start
# ===============================================================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    name = message.from_user.first_name or "دوست عزیز"
    text = (
        f"👋 سلام **{name}** عزیز!\n\n"
        "🎬 به ربات داینامیک **گپ فیلم** خوش آمدید!\n"
        "با هر بار کلیک، جدیدترین محتوای سایت به‌صورت زنده دریافت می‌شود.\n\n"
        "👇 یک گزینه را انتخاب کنید:"
    )
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=main_menu(),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


# ===============================================================
# 🔄 مدیریت دکمه‌های شیشه‌ای
# ===============================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    data = call.data

    bot.answer_callback_query(call.id, "⏳ در حال دریافت اطلاعات از سایت...")

    if data == "new_movies":
        bot.send_message(chat_id, "🔄 در حال دریافت جدیدترین فیلم‌ها از گپ فیلم...")
        items = fetch_latest_content(limit=6)
        movies = [i for i in items if i["type"] == "فیلم"]

        if not movies:
            movies = items  # اگر همه سریال بودند، همان‌ها را نشان بده

        send_content_list(chat_id, movies, "🎬 **جدیدترین فیلم‌های گپ فیلم**")

    elif data == "new_series":
        bot.send_message(chat_id, "🔄 در حال دریافت جدیدترین سریال‌ها از گپ فیلم...")
        items = fetch_latest_content(limit=8)
        series = [i for i in items if i["type"] == "سریال"]

        if not series:
            series = items

        send_content_list(chat_id, series, "📺 **جدیدترین سریال‌های گپ فیلم**")

    elif data == "top_rated":
        bot.send_message(chat_id, "🔄 در حال دریافت برترین‌ها...")
        items = fetch_latest_content(limit=8)
        # مرتب‌سازی بر اساس امتیاز IMDb
        items = sorted(
            [i for i in items if i["rating"]],
            key=lambda x: float(x["rating"]) if x["rating"].replace(".", "").isdigit() else 0,
            reverse=True,
        )
        send_content_list(chat_id, items[:6], "🔥 **برترین‌های گپ فیلم (بر اساس IMDb)**")


# ===============================================================
# 💬 پیام‌های متنی
# ===============================================================
@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.reply_to(
        message,
        "📩 پیام شما دریافت شد.\nبرای مشاهده منو از /start استفاده کنید.",
        reply_markup=main_menu(),
    )


# ===============================================================
# ▶️ اجرا
# ===============================================================
if __name__ == "__main__":
    print("🤖 ربات داینامیک گپ فیلم روشن شد...")
    bot.infinity_polling()
