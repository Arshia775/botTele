import os
import asyncio
import telebot
from telebot import types
from playwright.async_api import async_playwright

# ---------------------------------------------------------------
# 🔐 توکن ربات
# ---------------------------------------------------------------
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ توکن ربات تنظیم نشده است!")

bot = telebot.TeleBot(TOKEN)

BASE_URL = "https://gapfilm.ir"

# ===============================================================
# 🕷️ اسکرپر با Playwright
# ===============================================================
async def scrape_gapfilm(limit: int = 8):
    """
    با Playwright صفحه gapfilm.ir را باز می‌کند، صبر می‌کند
    جاوااسکریپت اجرا شود، سپس لینک‌های فیلم و سریال را استخراج می‌کند.
    """
    results = []
    seen = set()

    async with async_playwright() as p:
        # اجرای مرورگر به صورت Headless
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = await browser.new_context(
            locale="fa-IR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
        )

        page = await context.new_page()

        # مسدود کردن منابع غیرضروری برای سرعت بیشتر
        await page.route(
            "**/*",
            lambda route: asyncio.create_task(_block_resources(route)),
        )

        try:
            # باز کردن سایت
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)

            # صبر برای بارگذاری کارت‌های محتوا
            try:
                await page.wait_for_selector(
                    'a[href*="/movie/"], a[href*="/serial/"]',
                    timeout=20000,
                )
            except Exception:
                pass

            # کمی اسکرول برای بارگذاری Lazy Loading
            for _ in range(3):
                await page.mouse.wheel(0, 1500)
                await asyncio.sleep(1)

            # استخراج داده‌ها
            items = await page.evaluate("""
                () => {
                    const results = [];
                    const anchors = document.querySelectorAll(
                        'a[href*="/movie/"], a[href*="/serial/"]'
                    );
                    for (const a of anchors) {
                        const href = a.getAttribute('href') || '';
                        if (!href) continue;

                        let title = '';
                        let image = '';

                        const img = a.querySelector('img');
                        if (img) {
                            title = (img.getAttribute('alt') || '').trim();
                            image = img.getAttribute('src')
                                 || img.getAttribute('data-src')
                                 || '';
                            // اگر src نسبی است، کاملش کن
                            if (image && !image.startsWith('http')) {
                                image = 'https://gapfilm.ir' + image;
                            }
                        }

                        if (!title) {
                            const h3 = a.querySelector('h3');
                            if (h3) title = h3.innerText.trim();
                        }

                        if (!title) continue;

                        // امتیاز IMDb
                        let rating = '';
                        const ratingEl = a.querySelector('span.rait, .next-go0nwv .rait');
                        if (ratingEl) {
                            rating = ratingEl.innerText.trim();
                        }

                        results.push({
                            title: title,
                            link: href.startsWith('http')
                                  ? href
                                  : 'https://gapfilm.ir' + href,
                            image: image,
                            rating: rating,
                        });
                    }
                    return results;
                }
            """)

            # حذف تکراری‌ها و نگه‌داشتن ترتیب
            for it in items:
                if it["link"] in seen:
                    continue
                seen.add(it["link"])

                content_type = "سریال" if "/serial/" in it["link"] else "فیلم"
                it["type"] = content_type
                results.append(it)

                if len(results) >= limit * 2:
                    break

        finally:
            await browser.close()

    return results[:limit]


async def _block_resources(route):
    """مسدود کردن تصاویر بزرگ، فونت‌ها و آنالیتیکس برای سرعت."""
    try:
        req = route.request
        rtype = req.resource_type
        url = req.url.lower()

        # اجازه دسترسی به تصاویر کوچک برای پوستر فیلم‌ها
        if rtype in ("font", "media", "stylesheet"):
            return await route.abort()

        # مسدود کردن اسکریپت‌های تبلیغاتی/آنالیتیکس
        blocked = ("google-analytics", "googletagmanager", "doubleclick",
                   "yandex", "facebook", "hotjar", "clarity")
        if any(b in url for b in blocked):
            return await route.abort()

        await route.continue_()
    except Exception:
        try:
            await route.continue_()
        except Exception:
            pass


def scrape_sync(limit=8):
    """Wrapper برای فراخوانی async از کد sync تلگرام."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(scrape_gapfilm(limit))
    finally:
        try:
            loop.close()
        except Exception:
            pass


# ===============================================================
# 📤 ارسال محتوا به تلگرام
# ===============================================================
def send_content_list(chat_id, items, header):
    if not items:
        bot.send_message(
            chat_id,
            "😔 متأسفانه محتوایی از سایت دریافت نشد.\n"
            "لطفاً چند لحظه بعد دوباره امتحان کنید.",
        )
        return

    bot.send_message(chat_id, header, parse_mode="Markdown")

    for item in items:
        caption = f"🎬 **{item['title']}**\n📌 نوع: {item['type']}\n"
        if item.get("rating"):
            caption += f"⭐ IMDb: {item['rating']}\n"

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(
            text="▶️ مشاهده در گپ فیلم",
            url=item["link"],
        ))

        if item.get("image", "").startswith("http"):
            try:
                bot.send_photo(
                    chat_id,
                    photo=item["image"],
                    caption=caption,
                    reply_markup=kb,
                    parse_mode="Markdown",
                )
                continue
            except Exception as e:
                print(f"⚠️ ارسال عکس ناموفق: {e}")

        bot.send_message(
            chat_id,
            caption,
            reply_markup=kb,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )


# ===============================================================
# 🎛️ منوی اصلی
# ===============================================================
def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("🎬 جدیدترین فیلم‌ها", callback_data="new_movies"),
        types.InlineKeyboardButton("📺 جدیدترین سریال‌ها", callback_data="new_series"),
    )
    kb.row(
        types.InlineKeyboardButton("🔥 همه جدیدترین‌ها", callback_data="new_all"),
        types.InlineKeyboardButton("🔍 جستجو در سایت", url=f"{BASE_URL}/search/"),
    )
    kb.row(
        types.InlineKeyboardButton("📥 اپلیکیشن‌ها", url=f"{BASE_URL}/faq/7/"),
        types.InlineKeyboardButton("💳 خرید اشتراک", url=f"{BASE_URL}/landing/subscription/"),
    )
    return kb


# ===============================================================
# 🚀 دستورات
# ===============================================================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    name = message.from_user.first_name or "دوست عزیز"
    text = (
        f"👋 سلام **{name}** عزیز!\n\n"
        "🎬 به ربات داینامیک **گپ فیلم** خوش آمدید!\n"
        "با هر کلیک، جدیدترین محتوای سایت به‌صورت زنده دریافت می‌شود.\n\n"
        "👇 یک گزینه را انتخاب کنید:"
    )
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=main_menu(),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


@bot.message_handler(commands=["new"])
def cmd_new(message):
    bot.send_message(message.chat.id, "🔄 در حال دریافت جدیدترین‌ها از گپ فیلم...")
    items = scrape_sync(limit=8)
    send_content_list(message.chat.id, items, "🎬 **جدیدترین‌های گپ فیلم**")


# ===============================================================
# 🔄 Callback ها
# ===============================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    data = call.data

    bot.answer_callback_query(call.id, "⏳ در حال دریافت از سایت...")
    bot.send_message(chat_id, "🔄 در حال دریافت اطلاعات از گپ فیلم...\n(چند ثانیه صبر کنید)")

    items = scrape_sync(limit=10)

    if data == "new_movies":
        movies = [i for i in items if i["type"] == "فیلم"]
        send_content_list(chat_id, movies[:6], "🎬 **جدیدترین فیلم‌های گپ فیلم**")

    elif data == "new_series":
        series = [i for i in items if i["type"] == "سریال"]
        send_content_list(chat_id, series[:6], "📺 **جدیدترین سریال‌های گپ فیلم**")

    elif data == "new_all":
        send_content_list(chat_id, items[:8], "🔥 **جدیدترین‌های گپ فیلم**")


# ===============================================================
# 💬 پیام متنی
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
    print("🤖 ربات داینامیک گپ فیلم (Playwright) روشن شد...")
    bot.infinity_polling()
