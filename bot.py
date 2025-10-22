# bot.py
import json
import logging
from datetime import datetime, timedelta
import pytz

from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters

import firebase_admin
from firebase_admin import credentials, firestore

# --- Load config ---
with open('config.json', 'r') as f:
    cfg = json.load(f)

TELEGRAM_TOKEN = cfg['TELEGRAM_TOKEN']
MINE_AMOUNT = float(cfg.get('MINE_AMOUNT', 1.0))
MINE_COOLDOWN_HOURS = int(cfg.get('MINE_COOLDOWN_HOURS', 24))
REFERRAL_BONUS = float(cfg.get('REFERRAL_BONUS', 0.5))
ADMIN_IDS = cfg.get('ADMIN_IDS', [])

# --- Firebase init ---
cred = credentials.Certificate('serviceAccount.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Helpers
def get_user_doc(user_id):
    doc_ref = db.collection('users').document(str(user_id))
    doc = doc_ref.get()
    return doc_ref, doc

def create_user_if_not_exists(user_id, username=None, referrer=None):
    doc_ref = db.collection('users').document(str(user_id))
    doc = doc_ref.get()
    if not doc.exists:
        data = {
            'username': username or '',
            'balance': 0.0,
            'last_mine': None,
            'referrer': referrer,
            'invite_count': 0,
            'created_at': firestore.SERVER_TIMESTAMP
        }
        doc_ref.set(data)
        # increment invite_count for referrer if present
        if referrer:
            ref_ref = db.collection('users').document(str(referrer))
            ref = ref_ref.get()
            if ref.exists:
                ref_ref.update({'invite_count': firestore.Increment(1)})
        return doc_ref, data
    else:
        return doc_ref, doc.to_dict()

def record_claim(user_id, amount, claim_type='mine'):
    db.collection('claims').add({
        'user_id': str(user_id),
        'amount': float(amount),
        'type': claim_type,
        'time': firestore.SERVER_TIMESTAMP
    })

def human_time(dt):
    if not dt:
        return "Never"
    return dt.astimezone(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')

# Commands
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    args = context.args
    ref = None
    if args:
        # Handle invite link like /start 123456789
        try:
            ref = str(args[0])
        except:
            ref = None

    create_user_if_not_exists(user.id, user.username or user.full_name, referrer=ref)
    text = (
        f"🔥 Welcome {user.first_name}!\n\n"
        f"🎯 This is ChillBoi Miner\n"
        f"⚡ Mine {MINE_AMOUNT} CHILL per {MINE_COOLDOWN_HOURS} hours using /mine\n"
        f"🤝 Invite friends to get {REFERRAL_BONUS} CHILL each (they must use your link)\n\n"
        f"Commands:\n"
        f"/mine - Mine now\n"
        f"/balance - Show your balance\n"
        f"/invite - Get your invite link\n"
        f"/leaderboard - Top miners\n"
    )
    update.message.reply_text(text)

def mine(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    doc_ref, doc = get_user_doc(uid)
    if not doc.exists:
        create_user_if_not_exists(uid, user.username or user.full_name)

    data = doc.to_dict() if doc.exists else None
    last_mine = data.get('last_mine') if data else None

    now = datetime.utcnow()
    if last_mine:
        # Firestore timestamp to datetime
        last = last_mine
        if hasattr(last, 'to_datetime'):
            last = last.to_datetime()
        delta = now - last.replace(tzinfo=None) if hasattr(last, 'tzinfo') else now - last
        if delta < timedelta(hours=MINE_COOLDOWN_HOURS):
            remaining = timedelta(hours=MINE_COOLDOWN_HOURS) - delta
            hrs = int(remaining.total_seconds() // 3600)
            mins = int((remaining.total_seconds() % 3600) // 60)
            update.message.reply_text(f"⏳ You already mined. Come back in {hrs}h {mins}m.")
            return

    # Give mining reward
    doc_ref.update({
        'balance': firestore.Increment(MINE_AMOUNT),
        'last_mine': firestore.SERVER_TIMESTAMP
    })
    record_claim(uid, MINE_AMOUNT, 'mine')

    # Give referrer bonus if first time? We'll give ref bonus at signup time; here optionally give small extra
    update.message.reply_text(f"✅ You mined {MINE_AMOUNT} CHILL! Use /balance to view your balance.\nInvite friends: /invite")

def balance(update: Update, context: CallbackContext):
    user = update.effective_user
    doc_ref, doc = get_user_doc(user.id)
    if not doc.exists:
        create_user_if_not_exists(user.id, user.username or user.full_name)
        update.message.reply_text("You didn't have an account; created one. Use /mine to start.")
        return
    data = doc.to_dict()
    bal = data.get('balance', 0.0)
    last = data.get('last_mine')
    update.message.reply_text(f"👤 @{data.get('username') or user.first_name}\n💰 Balance: {bal} CHILL\n⏱ Last mined: {human_time(last)}")

def invite(update: Update, context: CallbackContext):
    user = update.effective_user
    link = f"https://t.me/{context.bot.username}?start={user.id}"
    update.message.reply_text(f"🔗 Invite link (share it):\n{link}\n\nEach friend who uses this link gives you {REFERRAL_BONUS} CHILL bonus!")

def leaderboard(update: Update, context: CallbackContext):
    # Query top 10 by balance
    users_ref = db.collection('users').order_by('balance', direction=firestore.Query.DESCENDING).limit(10)
    docs = users_ref.stream()
    text = "🏆 Top miners (by balance):\n\n"
    i = 1
    for d in docs:
        u = d.to_dict()
        uname = u.get('username') or 'Unknown'
        bal = u.get('balance', 0.0)
        text += f"{i}. @{uname} — {bal} CHILL\n"
        i += 1
    update.message.reply_text(text)

def admin_add(update: Update, context: CallbackContext):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        update.message.reply_text("🚫 Not allowed.")
        return
    # Usage: /add user_id amount
    args = context.args
    if len(args) < 2:
        update.message.reply_text("Usage: /add <telegram_id> <amount>")
        return
    uid = args[0]
    amt = float(args[1])
    doc_ref = db.collection('users').document(str(uid))
    doc_ref.update({'balance': firestore.Increment(amt)})
    record_claim(uid, amt, 'admin_add')
    update.message.reply_text(f"✅ Added {amt} CHILL to {uid}.")

def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start, pass_args=True))
    dp.add_handler(CommandHandler('mine', mine))
    dp.add_handler(CommandHandler('balance', balance))
    dp.add_handler(CommandHandler('invite', invite))
    dp.add_handler(CommandHandler('leaderboard', leaderboard))
    dp.add_handler(CommandHandler('add', admin_add))

    updater.start_polling()
    logger.info("Bot started")
    updater.idle()

if __name__ == '__main__':
    main()
