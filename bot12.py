import sqlite3
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    filters, ConversationHandler
)
from telegram.error import BadRequest

# === CONFIG ===
BOT_TOKEN = "7519758382:AAFiv1X-BPL7eiUclV3fv0jGv8lOWlIpMsE"
ADMINS = [7618902229]
CHANNELS_FILE = "channels.txt"

# === STATES ===
ASK_CHANNEL_ID, ASK_USERNAME = range(2)
WAITING_KEYWORD = 2
ASK_DELETE = 3
ASK_EDIT_OLD = 4
ASK_EDIT_NEW = 5

# === DB ===
conn = sqlite3.connect("videos.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS videos (
    keyword TEXT,
    file_id TEXT,
    file_type TEXT,
    caption TEXT
)""")
cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
conn.commit()

# === CHANNEL FUNCTIONS ===
def get_channels():
    try:
        with open(CHANNELS_FILE, "r") as f:
            return [line.strip().split("|") for line in f if "|" in line]
    except FileNotFoundError:
        return []

def save_channel(channel_id, username):
    if [channel_id, username] not in get_channels():
        with open(CHANNELS_FILE, "a") as f:
            f.write(f"{channel_id}|{username}\n")

def remove_channel(channel_id):
    chs = get_channels()
    with open(CHANNELS_FILE, "w") as f:
        for cid, uname in chs:
            if cid != channel_id:
                f.write(f"{cid}|{uname}\n")

# === OBUNA TEKSHIRISH ===
async def is_subscribed_all(user_id, context):
    unsubscribed = []
    for ch_id, username in get_channels():
        try:
            member = await context.bot.get_chat_member(ch_id, user_id)
            if member.status not in ("member", "administrator", "creator"):
                unsubscribed.append(username)
        except:
            unsubscribed.append(username)
    return (len(unsubscribed) == 0, unsubscribed)

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

    is_sub, not_subs = await is_subscribed_all(user_id, context)
    if not is_sub:
        buttons = [[InlineKeyboardButton("🔔 Obuna bo‘lish", url=f"https://t.me/{ch}")] for ch in not_subs]
        await update.message.reply_text("❗ Quyidagi kanallarga obuna bo‘ling va botga /start yuboring:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    args = context.args
    if args:
        keyword = args[0].strip().lower()
        cur.execute("SELECT file_id, file_type, caption FROM videos WHERE keyword = ?", (keyword,))
        res = cur.fetchall()
        if res:
            msg = await update.message.reply_text("🔍 Fayllar topildi...")
            await asyncio.sleep(1)
            await msg.delete()
            for file_id, file_type, caption in res:
                try:
                    if file_type == "video":
                        await update.message.reply_video(file_id, caption=caption)
                    elif file_type == "gif":
                        await update.message.reply_animation(file_id, caption=caption)
                    elif file_type == "photo":
                        await update.message.reply_photo(file_id, caption=caption)
                    elif file_type in ["zip", "apk"]:
                        await update.message.reply_document(file_id, caption=caption)
                except:
                    pass
        else:
            await update.message.reply_text("❌ Fayl topilmadi.")
    else:
        await update.message.reply_text("👋 Assalomu alaykum!\n📥 Kalit so‘z yuboring, men sizga fayl topib beraman.")

# === QIDIRUV ===
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_sub, not_subs = await is_subscribed_all(user_id, context)
    if not is_sub:
        buttons = [[InlineKeyboardButton("🔔 Obuna bo‘lish", url=f"https://t.me/{ch}")] for ch in not_subs]
        await update.message.reply_text("❗ Quyidagi kanallarga obuna bo‘ling:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    keyword = update.message.text.strip().lower()
    cur.execute("SELECT file_id, file_type, caption FROM videos WHERE keyword = ?", (keyword,))
    res = cur.fetchall()
    if res:
        msg = await update.message.reply_text(f"🔍 '{keyword}' bo‘yicha topilgan fayllar:")
        await asyncio.sleep(3)
        await msg.delete()
        for file_id, file_type, caption in res:
            try:
                if file_type == "video":
                    await update.message.reply_video(file_id, caption=caption)
                elif file_type == "gif":
                    await update.message.reply_animation(file_id, caption=caption)
                elif file_type == "photo":
                    await update.message.reply_photo(file_id, caption=caption)
                elif file_type in ["zip", "apk"]:
                    await update.message.reply_document(file_id, caption=caption)
            except:
                pass
    else:
        await update.message.reply_text("❌ Fayl topilmadi.")

# === 2-STEP ADMIN YUKLASH ===
WAITING_KEYWORD = 5
admin_media_cache = {}

async def upload_step1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        return
    message = update.message
    file_id, file_type = None, None

    if message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.animation:
        file_id = message.animation.file_id
        file_type = "gif"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        mime = message.document.mime_type
        file_id = message.document.file_id
        if mime.endswith("zip"):
            file_type = "zip"
        elif mime == "application/vnd.android.package-archive":
            file_type = "apk"

    if file_id and file_type:
        admin_media_cache[user_id] = {
            "file_id": file_id,
            "file_type": file_type,
            "caption": message.caption or ""
        }
        await update.message.reply_text("📝 Kalit so‘z yuboring:")
        return WAITING_KEYWORD
    else:
        await update.message.reply_text("❗ Yuborilgan media turini aniqlab bo‘lmadi.")

async def upload_step2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyword = update.message.text.strip().lower()
    media = admin_media_cache.get(user_id)

    if media:
        cur.execute("INSERT INTO videos (keyword, file_id, file_type, caption) VALUES (?, ?, ?, ?)",
                    (keyword, media["file_id"], media["file_type"], media["caption"]))
        conn.commit()
        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={keyword}"
        await update.message.reply_text(f"✅ Saqlandi\n🔗 {link}")
        del admin_media_cache[user_id]
    else:
        await update.message.reply_text("❗ Xatolik yuz berdi.")
    return ConversationHandler.END

# === /stat ===
async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    cur.execute("SELECT COUNT(*) FROM users")
    u = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM videos")
    v = cur.fetchone()[0]
    await update.message.reply_text(f"👤 Foydalanuvchilar: {u}\n🎞 Fayllar: {v}")

# === /channel ===
async def show_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chs = get_channels()
    if not chs:
        await update.message.reply_text("📭 Hech qanday kanal yo‘q.")
        return
    msg = "\n".join([f"{cid} | @{uname}" for cid, uname in chs])
    await update.message.reply_text(f"📋 Kanallar:\n\n{msg}")

# === /addchannel ===
ASK_CHANNEL_ID, ASK_USERNAME = range(2)

async def addchannel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return await update.message.reply_text("❌ Ruxsat yo‘q.")
    await update.message.reply_text("📥 Kanal ID ni kiriting:")
    return ASK_CHANNEL_ID

async def addchannel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["channel_id"] = update.message.text.strip()
    await update.message.reply_text("📛 Kanal username kiriting:")
    return ASK_USERNAME

async def addchannel_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_id = context.user_data.get("channel_id")
    username = update.message.text.strip().lstrip("@")
    save_channel(channel_id, username)
    await update.message.reply_text("✅ Kanal qo‘shildi.")
    return ConversationHandler.END

# === /removechannel ===
async def removechannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    if not context.args:
        return await update.message.reply_text("🗑 Kanal ID kiriting.")
    remove_channel(context.args[0])
    await update.message.reply_text("✅ Kanal o‘chirildi.")
async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    cur.execute("SELECT COUNT(*) FROM users")
    u = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM videos")
    v = cur.fetchone()[0]
    await update.message.reply_text(f"👤 Foydalanuvchilar: {u}\n🎞 Fayllar: {v}")

async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    await update.message.reply_text("🗑 O‘chirmoqchi bo‘lgan **kalit so‘z**ni kiriting:")
    return ASK_DELETE

async def delete_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text.strip().lower()
    cur.execute("DELETE FROM videos WHERE keyword = ?", (keyword,))
    conn.commit()
    await update.message.reply_text("✅ O‘chirildi.")
    return ConversationHandler.END

async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return
    await update.message.reply_text("✏️ Eski kalit so‘zni kiriting:")
    return ASK_EDIT_OLD

async def edit_old(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["old_keyword"] = update.message.text.strip().lower()
    await update.message.reply_text("🆕 Yangi kalit so‘zni kiriting:")
    return ASK_EDIT_NEW

async def edit_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_keyword = update.message.text.strip().lower()
    old_keyword = context.user_data.get("old_keyword")
    cur.execute("UPDATE videos SET keyword = ? WHERE keyword = ?", (new_keyword, old_keyword))
    conn.commit()
    await update.message.reply_text("✅ Kalit so‘z yangilandi.")
    return ConversationHandler.END
    
# === RUN ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stat", stat))
    app.add_handler(CommandHandler("channel", show_channels))
    app.add_handler(CommandHandler("removechannel", removechannel))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("addchannel", addchannel_start)],
        states={
            ASK_CHANNEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, addchannel_id)],
            ASK_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, addchannel_username)],
        },
        fallbacks=[]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(
            (filters.VIDEO | filters.PHOTO | filters.ANIMATION | filters.Document.ALL) & filters.User(ADMINS),
            upload_step1)],
        states={
            WAITING_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_step2)]
        },
        fallbacks=[]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete", delete_start)],
        states={
            ASK_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_keyword)]
        },
        fallbacks=[]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("edit", edit_start)],
        states={
            ASK_EDIT_OLD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_old)],
            ASK_EDIT_NEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_new)],
        },
        fallbacks=[]
    ))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))

    print("✅ Bot ishga tushdi!")
    app.run_polling()


if __name__ == "__main__":
    main()