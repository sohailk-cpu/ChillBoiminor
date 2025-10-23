from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import firebase_admin
from firebase_admin import credentials, firestore

# 🔥 Firebase Setup
cred = credentials.Certificate("firebase.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

TOKEN = "8122507216:AAFlRzkV8kvPhfMQZv8FhnPMpvJwdUnpsDI"

# 🪙 /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_ref = db.collection("users").document(user_id)
    user = user_ref.get()

    if not user.exists:
        user_ref.set({"balance": 0, "lastTap": 0})
        await update.message.reply_text("Welcome to ChillCoin 💰\nStart tapping to earn your first coin!")
    else:
        await update.message.reply_text("Welcome back to ChillCoin 😎\nType /mine to earn coins.")

# 💰 /mine command
async def mine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_ref = db.collection("users").document(user_id)
    user = user_ref.get()

    if user.exists:
        current_balance = user.to_dict()["balance"] + 1
        user_ref.update({"balance": current_balance})
        await update.message.reply_text(f"🪙 You mined 1 ChillCoin!\n💵 Total Balance: {current_balance}")
    else:
        await update.message.reply_text("Please start first using /start")

# 📊 /balance command
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_ref = db.collection("users").document(user_id)
    user = user_ref.get()

    if user.exists:
        bal = user.to_dict()["balance"]
        await update.message.reply_text(f"💵 Your ChillCoin Balance: {bal}")
    else:
        await update.message.reply_text("Please start first using /start")

# 🚀 Run Bot
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("mine", mine))
app.add_handler(CommandHandler("balance", balance))

app.run_polling()
