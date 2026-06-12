import logging
import sqlite3
import os
from datetime import datetime

from telegram import Update
from telegram.ext import Application, ChatMemberHandler, CommandHandler, ContextTypes
from telegram.constants import ChatMemberStatus

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---- Configurare din variabile de mediu (le setezi pe Railway) ----
BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = int(os.environ["GROUP_CHAT_ID"])  # grupul cu CLIENȚII (Maxim/Zevs)
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))  # grupul PRIVAT, doar admini

DB_PATH = "clients.db"


# ---- Bază de date simplă (SQLite) ----
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS clients (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            source TEXT,
            joined_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def save_client(user_id, username, full_name, source):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO clients (user_id, username, full_name, source, joined_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, username or "", full_name or "", source, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# ---- Generare link-uri unice (rulezi o singură dată) ----
async def generate_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comandă: /generate_links — creează 2 link-uri de invitație, unul pentru Maxim, unul pentru Zevs."""
    try:
        link_maxim = await context.bot.create_chat_invite_link(
            chat_id=GROUP_CHAT_ID, name="Maxim"
        )
        link_zevs = await context.bot.create_chat_invite_link(
            chat_id=GROUP_CHAT_ID, name="Zevs"
        )
        text = (
            "✅ Link-uri create cu succes!\n\n"
            f"🔗 Link Maxim:\n{link_maxim.invite_link}\n\n"
            f"🔗 Link Zevs:\n{link_zevs.invite_link}\n\n"
            "Trimite fiecare admin linkul lui pe TikTok/Instagram."
        )
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"❌ Eroare: {e}")


async def chat_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"ID-ul acestui chat este: {update.effective_chat.id}")


# ---- Detectare membru nou ----
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.chat_member
    if cm.chat.id != GROUP_CHAT_ID:
        return

    old_status = cm.old_chat_member.status
    new_status = cm.new_chat_member.status

    joined_now = old_status in (
        ChatMemberStatus.LEFT,
        ChatMemberStatus.BANNED,
        ChatMemberStatus.RESTRICTED,
    ) and new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED)

    if not joined_now:
        return

    user = cm.new_chat_member.user
    invite_link = cm.invite_link
    source = invite_link.name if invite_link and invite_link.name else "Necunoscut"

    display_name = f"@{user.username}" if user.username else user.full_name

    save_client(user.id, user.username, user.full_name, source)

    text = f"✅ {display_name} a venit prin {source}"
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=text)


# ---- /stats ----
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT source, COUNT(*) FROM clients GROUP BY source ORDER BY COUNT(*) DESC")
    rows = c.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Nu sunt date încă.")
        return

    text = "📊 Statistici clienți:\n\n"
    total = 0
    for source, count in rows:
        text += f"• {source}: {count} clienți\n"
        total += count
    text += f"\nTotal: {total} clienți"

    await update.message.reply_text(text)


# ---- /cauta @username ----
async def cauta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if not context.args:
        await update.message.reply_text("Folosire: /cauta @username")
        return

    username = context.args[0].lstrip("@").lower()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT source, joined_at, full_name FROM clients WHERE LOWER(username) = ?",
        (username,),
    )
    row = c.fetchone()
    conn.close()

    if row:
        source, joined_at, full_name = row
        data = joined_at[:10]
        await update.message.reply_text(
            f"👤 {full_name} (@{username})\n"
            f"📍 Sursă: {source}\n"
            f"📅 Intrat în grup: {data}"
        )
    else:
        await update.message.reply_text(f"Nu am găsit @{username} în baza de date.")


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("cauta", cauta))
    app.add_handler(CommandHandler("generate_links", generate_links))
    app.add_handler(CommandHandler("id", chat_id_command))

    logger.info("Bot pornit...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
