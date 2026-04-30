# H.py - COMPLETE FIXED VERSION FOR RENDER WITH ADMIN PERMISSIONS TOGGLE & BANKING SYSTEM
import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import signal
import threading
import re
import sys
import atexit
import requests
import pymongo
from flask import Flask
from threading import Thread

# ====================== RENDER CONFIGURATION ======================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join('/tmp', 'upload_bots')
IROTECH_DIR = os.path.join('/tmp', 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot is running on Render!"

@app.route('/health')
def health():
    return json.dumps({'status': 'ok', 'uptime': get_uptime()})

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8713065612:AAFjB0OJl21_lNPuDPF017byvVcfEwhKC9Y')
OWNER_ID = int(os.environ.get('OWNER_ID', 8477195695))
ADMIN_ID = int(os.environ.get('ADMIN_ID', 8477195695))
YOUR_USERNAME = os.environ.get('YOUR_USERNAME', '@BGMI_main')
UPDATE_CHANNEL = os.environ.get('UPDATE_CHANNEL', 'https://t.me/UROGGY')

A4F_API_URL = "https://samuraiapi.in/v1/chat/completions"
A4F_API_KEY = "sk-NK6SS9tpWghyFJwkZLoCis1sMaF6RwQ5WF09mUoKKR0VKCm7"
A4F_MODEL = "provider10-claude-sonnet-4-20250514(clinesp)"

BOT_START_TIME = datetime.now()

def get_uptime():
    uptime = datetime.now() - BOT_START_TIME
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

FREE_USER_LIMIT = 2
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 99
OWNER_LIMIT = float('inf')

bot = telebot.TeleBot(TOKEN)

bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ====================== MONGODB CONNECTION FOR PERMISSIONS & BANKING ======================
MONGO_URL = "mongodb+srv://userbot:userbot@cluster0.iweqz.mongodb.net/test?retryWrites=true&w=majority"
try:
    mongo_client = pymongo.MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    mongo_client.admin.command('ping')
    mongo_db = mongo_client['telegram_bot']
    admin_perms_col = mongo_db['admin_permissions']
    banking_col = mongo_db['user_banking']
    logger.info("✅ MongoDB connected successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    mongo_db = None
    admin_perms_col = None
    banking_col = None

# Permission flags (for non-owner admins)
PERMISSIONS_LIST = [
    'approve_files',      # Can approve/reject uploaded files
    'broadcast',          # Can broadcast messages
    'manage_subscriptions', # Can add/remove subscriptions
    'lock_bot',           # Can lock/unlock bot
    'run_all_scripts',    # Can run all user scripts
    'manage_admins',      # Can add/remove other admins (owner only anyway)
    'banking'             # Can modify user balances
]

def init_admin_permissions(admin_id):
    """Initialize default permissions for an admin (all True except manage_admins)"""
    if admin_perms_col is None: return
    existing = admin_perms_col.find_one({'admin_id': admin_id})
    if not existing:
        default_perms = {perm: True for perm in PERMISSIONS_LIST}
        default_perms['manage_admins'] = False  # only owner can manage admins
        admin_perms_col.insert_one({'admin_id': admin_id, 'permissions': default_perms})
        logger.info(f"Initialized permissions for admin {admin_id}")

def get_admin_permissions(admin_id):
    """Return dict of permissions for given admin_id"""
    if admin_perms_col is None:
        # Fallback: all True if MongoDB not available (but owner check still applies)
        return {perm: True for perm in PERMISSIONS_LIST}
    doc = admin_perms_col.find_one({'admin_id': admin_id})
    if doc:
        return doc.get('permissions', {})
    else:
        init_admin_permissions(admin_id)
        return get_admin_permissions(admin_id)

def update_admin_permission(admin_id, permission, value):
    """Set a specific permission for an admin"""
    if admin_perms_col is None: return False
    result = admin_perms_col.update_one(
        {'admin_id': admin_id},
        {'$set': {f'permissions.{permission}': value}}
    )
    return result.modified_count > 0

def check_admin_permission(admin_id, permission):
    """Check if admin has a specific permission (owner always has all)"""
    if admin_id == OWNER_ID:
        return True
    perms = get_admin_permissions(admin_id)
    return perms.get(permission, False)

# ====================== BANKING SYSTEM ======================
def get_balance(user_id):
    if banking_col is None: return 0
    doc = banking_col.find_one({'user_id': user_id})
    return doc.get('balance', 0) if doc else 0

def set_balance(user_id, new_balance):
    if banking_col is None: return False
    banking_col.update_one({'user_id': user_id}, {'$set': {'balance': new_balance}}, upsert=True)
    return True

def add_balance(user_id, amount):
    curr = get_balance(user_id)
    new_bal = curr + amount
    set_balance(user_id, new_bal)
    return new_bal

def deduct_balance(user_id, amount):
    curr = get_balance(user_id)
    if curr < amount:
        return None
    new_bal = curr - amount
    set_balance(user_id, new_bal)
    return new_bal

# file approval status constants
FILE_STATUS_PENDING = "pending"
FILE_STATUS_APPROVED = "approved"
FILE_STATUS_REJECTED = "rejected"

COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel", "⏱ Uptime"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💰 Balance", "🤖 MPX Ai"],
    ["📞 Contact Owner"]
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel", "/ping"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💰 Balance", "💳 Subscriptions"],
    ["📢 Broadcast", "🔒 Lock Bot"],
    ["🟢 Running All Code", "👑 Admin Panel"],
    ["🤖 MPX Ai", "⏱ Uptime"],
    ["📞 Contact Owner"]
]

# ====================== SQLITE DB FUNCTIONS (unchanged from original) ======================
def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files (user_id INTEGER, file_name TEXT, file_type TEXT, PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS file_approvals (user_id INTEGER, file_name TEXT, status TEXT, reviewed_by INTEGER, review_time TEXT, file_type TEXT, uploaded_time TEXT, message_id INTEGER, PRIMARY KEY (user_id, file_name))''')
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"Invalid expiry date format for user {user_id}: {expiry}. Skipping.")
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))
        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())
        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users, {len(user_subscriptions)} subscriptions, {len(admin_ids)} admins.")
    except Exception as e:
        logger.error(f"Error loading data: {e}", exc_info=True)

init_db()
load_data()

# Initialize permissions for existing admins in MongoDB if available
if admin_perms_col is not None:
    for aid in admin_ids:
        init_admin_permissions(aid)

# ====================== FILE APPROVAL HELPERS (unchanged) ======================
DB_LOCK = threading.Lock()
def save_file_approval(user_id, file_name, file_type, status=FILE_STATUS_PENDING, reviewed_by=None, message_id=None):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            uploaded_time = datetime.now().isoformat()
            review_time = datetime.now().isoformat() if reviewed_by else None
            c.execute('''INSERT OR REPLACE INTO file_approvals (user_id, file_name, file_type, status, reviewed_by, review_time, uploaded_time, message_id) VALUES (?,?,?,?,?,?,?,?)''',
                     (user_id, file_name, file_type, status, reviewed_by, review_time, uploaded_time, message_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving file approval: {e}", exc_info=True)
        finally:
            conn.close()

def get_file_status(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT status, reviewed_by, review_time, file_type FROM file_approvals WHERE user_id=? AND file_name=?', (user_id, file_name))
            result = c.fetchone()
            if result:
                return {'status': result[0], 'reviewed_by': result[1], 'review_time': result[2], 'file_type': result[3]}
            return {'status': FILE_STATUS_PENDING, 'file_type': 'unknown'}
        except Exception as e:
            logger.error(f"Error getting file status: {e}")
            return {'status': FILE_STATUS_PENDING, 'file_type': 'unknown'}
        finally:
            conn.close()

def update_file_status(user_id, file_name, status, admin_id):
    if not check_admin_permission(admin_id, 'approve_files'):
        return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            review_time = datetime.now().isoformat()
            c.execute('UPDATE file_approvals SET status=?, reviewed_by=?, review_time=? WHERE user_id=? AND file_name=?', (status, admin_id, review_time, user_id, file_name))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating file status: {e}")
            return False
        finally:
            conn.close()

def get_all_pending_files():
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT user_id, file_name, file_type, uploaded_time FROM file_approvals WHERE status=? ORDER BY uploaded_time DESC', (FILE_STATUS_PENDING,))
            return c.fetchall()
        except Exception as e:
            logger.error(f"Error getting pending files: {e}")
            return []
        finally:
            conn.close()

def get_pending_files_count():
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT COUNT(*) FROM file_approvals WHERE status=?', (FILE_STATUS_PENDING,))
            return c.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting pending files count: {e}")
            return 0
        finally:
            conn.close()

def send_file_for_approval(message, user_id, file_name, file_type):
    user = message.from_user
    file_info = (f"📄 **NEW FILE FOR APPROVAL**\n\n👤 **User:** {user.first_name}\n📛 **Username:** @{user.username or 'N/A'}\n🆔 **User ID:** `{user_id}`\n📁 **File:** `{file_name}`\n📊 **Type:** {file_type}\n🕐 **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n**Choose action:**")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f'approve_{user_id}_{file_name}'), types.InlineKeyboardButton("❌ Reject", callback_data=f'reject_{user_id}_{file_name}'))
    for admin_id in admin_ids:
        if check_admin_permission(admin_id, 'approve_files'):
            try:
                bot.forward_message(admin_id, message.chat.id, message.message_id)
                bot.send_message(admin_id, file_info, reply_markup=markup, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Failed to send file for approval to admin {admin_id}: {e}")

# ====================== MISC HELPERS (unchanged from original – only keep necessary) ======================
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not is_running:
                if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                    try: script_info['log_file'].close()
                    except: pass
                if script_key in bot_scripts: del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                try: script_info['log_file'].close()
                except: pass
            if script_key in bot_scripts: del bot_scripts[script_key]
            return False
    return False

def kill_process_tree(process_info):
    pid = None
    try:
        if 'log_file' in process_info and hasattr(process_info['log_file'], 'close') and not process_info['log_file'].closed:
            try: process_info['log_file'].close()
            except: pass
        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            pid = process.pid
            if pid:
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        try: child.terminate()
                        except: pass
                    gone, alive = psutil.wait_procs(children, timeout=1)
                    for p in alive: p.kill()
                    parent.terminate()
                    parent.wait(timeout=1)
                except psutil.NoSuchProcess: pass
    except Exception as e:
        logger.error(f"Error killing process tree: {e}")

# ====================== RUN SCRIPT FUNCTIONS (unchanged from original – abbreviated) ======================
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'flask': 'Flask',
    'requests': 'requests',
    'psutil': 'psutil'
}

def attempt_install_pip(module_name, message):
    package_name = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    if package_name is None: return False
    try:
        bot.reply_to(message, f"Installing {package_name}...")
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', package_name], capture_output=True, text=True)
        if result.returncode == 0:
            bot.reply_to(message, f"Installed {package_name}")
            return True
        else:
            bot.reply_to(message, f"Failed to install {package_name}")
            return False
    except Exception as e:
        logger.error(f"Install error: {e}")
        return False

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    file_status = get_file_status(script_owner_id, file_name)
    if file_status['status'] != FILE_STATUS_APPROVED:
        bot.reply_to(message_obj_for_reply, f"❌ File `{file_name}` not approved yet. Status: {file_status['status']}", parse_mode='Markdown')
        return
    script_key = f"{script_owner_id}_{file_name}"
    if not os.path.exists(script_path):
        bot.reply_to(message_obj_for_reply, f"Error: Script not found.")
        return
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        process = subprocess.Popen([sys.executable, script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.PIPE)
        bot_scripts[script_key] = {'process': process, 'log_file': log_file, 'file_name': file_name, 'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id, 'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'py'}
        bot.reply_to(message_obj_for_reply, f"Python script '{file_name}' started! (PID: {process.pid})")
    except Exception as e:
        bot.reply_to(message_obj_for_reply, f"Error: {e}")

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    file_status = get_file_status(script_owner_id, file_name)
    if file_status['status'] != FILE_STATUS_APPROVED:
        bot.reply_to(message_obj_for_reply, f"❌ File `{file_name}` not approved yet.", parse_mode='Markdown')
        return
    script_key = f"{script_owner_id}_{file_name}"
    if not os.path.exists(script_path):
        bot.reply_to(message_obj_for_reply, f"Error: Script not found.")
        return
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        process = subprocess.Popen(['node', script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.PIPE)
        bot_scripts[script_key] = {'process': process, 'log_file': log_file, 'file_name': file_name, 'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id, 'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'js'}
        bot.reply_to(message_obj_for_reply, f"JS script '{file_name}' started! (PID: {process.pid})")
    except Exception as e:
        bot.reply_to(message_obj_for_reply, f"Error: {e}")

def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?,?,?)', (user_id, file_name, file_type))
        conn.commit()
        if user_id not in user_files: user_files[user_id] = []
        user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name] + [(file_name, file_type)]
        conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM user_files WHERE user_id=? AND file_name=?', (user_id, file_name))
        conn.commit()
        if user_id in user_files:
            user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
            if not user_files[user_id]: del user_files[user_id]
        conn.close()

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()

def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?,?)', (user_id, expiry.isoformat()))
        conn.commit()
        user_subscriptions[user_id] = {'expiry': expiry}
        conn.close()

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM subscriptions WHERE user_id=?', (user_id,))
        conn.commit()
        if user_id in user_subscriptions: del user_subscriptions[user_id]
        conn.close()

def add_admin_db(admin_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (admin_id,))
        conn.commit()
        admin_ids.add(admin_id)
        conn.close()
    if admin_perms_col is not None:
        init_admin_permissions(admin_id)

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID: return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM admins WHERE user_id=?', (admin_id,))
        conn.commit()
        removed = c.rowcount > 0
        admin_ids.discard(admin_id)
        conn.close()
    return removed

# ====================== INLINE MENUS & MESSAGE HANDLERS ======================
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL),
        types.InlineKeyboardButton('📤 Upload File', callback_data='upload'),
        types.InlineKeyboardButton('📂 Check Files', callback_data='check_files'),
        types.InlineKeyboardButton('⚡ Bot Speed', callback_data='speed'),
        types.InlineKeyboardButton('📊 Statistics', callback_data='stats'),
        types.InlineKeyboardButton('💰 Balance', callback_data='balance'),
        types.InlineKeyboardButton('🤖 MPX AI', callback_data='mpx_ai'),
        types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}')
    ]
    if user_id == OWNER_ID or (user_id in admin_ids and check_admin_permission(user_id, 'manage_subscriptions')):
        buttons.insert(4, types.InlineKeyboardButton('💳 Subscriptions', callback_data='subscription'))
    if user_id == OWNER_ID or (user_id in admin_ids and check_admin_permission(user_id, 'broadcast')):
        buttons.insert(5, types.InlineKeyboardButton('📢 Broadcast', callback_data='broadcast'))
    if user_id == OWNER_ID or (user_id in admin_ids and check_admin_permission(user_id, 'lock_bot')):
        lock_text = '🔒 Lock Bot' if not bot_locked else '🔓 Unlock Bot'
        lock_cb = 'lock_bot' if not bot_locked else 'unlock_bot'
        buttons.append(types.InlineKeyboardButton(lock_text, callback_data=lock_cb))
    if user_id == OWNER_ID or (user_id in admin_ids and check_admin_permission(user_id, 'run_all_scripts')):
        buttons.append(types.InlineKeyboardButton('🟢 Run All Scripts', callback_data='run_all_scripts'))
    if user_id == OWNER_ID:
        buttons.append(types.InlineKeyboardButton('👑 Admin Permissions', callback_data='admin_perms_panel'))
    if user_id in admin_ids:
        buttons.append(types.InlineKeyboardButton('👑 Admin Panel', callback_data='admin_panel'))
    markup.add(*buttons[:2])  # row1
    markup.add(*buttons[2:4]) # row2
    markup.add(*buttons[4:6]) # row3
    remaining = buttons[6:]
    for i in range(0, len(remaining), 2):
        markup.add(*remaining[i:i+2])
    markup.add(types.InlineKeyboardButton('⏱ Uptime', callback_data='uptime'))
    return markup

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row in layout:
        markup.add(*[types.KeyboardButton(text) for text in row])
    return markup

def create_control_buttons(script_owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    file_status = get_file_status(script_owner_id, file_name)
    status_text = "✅ Approved" if file_status['status'] == FILE_STATUS_APPROVED else "⏳ Pending" if file_status['status'] == FILE_STATUS_PENDING else "❌ Rejected"
    if is_running:
        markup.row(types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{script_owner_id}_{file_name}'), types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{script_owner_id}_{file_name}'))
        markup.row(types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'), types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}'))
    else:
        markup.row(types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{script_owner_id}_{file_name}'), types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'))
        markup.row(types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton(f"Status: {status_text}", callback_data=f'status_{script_owner_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("🔙 Back to Files", callback_data='check_files'))
    return markup

def create_admin_permissions_panel(admin_id_for_perms):
    """Create inline keyboard to toggle permissions for a given admin (owner only)"""
    perms = get_admin_permissions(admin_id_for_perms)
    markup = types.InlineKeyboardMarkup(row_width=2)
    for perm in PERMISSIONS_LIST:
        status = "✅" if perms.get(perm, False) else "❌"
        cb = f'toggle_perm_{admin_id_for_perms}_{perm}'
        markup.add(types.InlineKeyboardButton(f"{status} {perm.replace('_', ' ').title()}", callback_data=cb))
    markup.add(types.InlineKeyboardButton("🔙 Back to Admin List", callback_data='admin_perms_list'))
    return markup

def create_admin_list_for_perms():
    """List all admins (including owner) for permission management"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    for aid in sorted(admin_ids):
        label = f"👑 {'Owner' if aid == OWNER_ID else 'Admin'} {aid}"
        markup.add(types.InlineKeyboardButton(label, callback_data=f'admin_perm_edit_{aid}'))
    markup.add(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    if check_admin_permission(OWNER_ID, 'manage_admins'):  # only owner can manage admins
        markup.row(types.InlineKeyboardButton('➕ Add Admin', callback_data='add_admin'), types.InlineKeyboardButton('➖ Remove Admin', callback_data='remove_admin'))
        markup.row(types.InlineKeyboardButton('📋 List Admins', callback_data='list_admins'))
    if check_admin_permission(OWNER_ID, 'manage_admins') or check_admin_permission(OWNER_ID, 'banking'):
        markup.row(types.InlineKeyboardButton('💸 Banking', callback_data='banking_panel'))
    markup.row(types.InlineKeyboardButton('📋 Pending Files', callback_data='view_pending'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_banking_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton('➕ Add Balance', callback_data='add_balance'), types.InlineKeyboardButton('➖ Deduct Balance', callback_data='deduct_balance'))
    markup.add(types.InlineKeyboardButton('🔙 Back to Admin Panel', callback_data='admin_panel'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    if check_admin_permission(OWNER_ID, 'manage_subscriptions'):
        markup.row(types.InlineKeyboardButton('➕ Add Subscription', callback_data='add_subscription'), types.InlineKeyboardButton('➖ Remove Subscription', callback_data='remove_subscription'))
        markup.row(types.InlineKeyboardButton('🔍 Check Subscription', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

# ====================== BALANCE COMMAND ======================
@bot.message_handler(commands=['balance'])
def balance_command(message):
    user_id = message.from_user.id
    bal = get_balance(user_id)
    bot.reply_to(message, f"💰 Your balance: `{bal}` coins", parse_mode='Markdown')

# ====================== MESSAGE HANDLERS ======================
def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "Bot locked by admin. Try later.")
        return
    if user_id not in active_users:
        add_active_user(user_id)
        try:
            owner_notification = f"New user!\nName: {user_name}\nID: `{user_id}`"
            bot.send_message(OWNER_ID, owner_notification, parse_mode='Markdown')
        except: pass
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    expiry_info = ""
    if user_id == OWNER_ID: user_status = "Owner"
    elif user_id in admin_ids: user_status = "Admin"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            user_status = "Premium"
            days_left = (expiry_date - datetime.now()).days
            expiry_info = f"\nSub expires in: {days_left} days"
        else: user_status = "Free User"
    else: user_status = "Free User"
    welcome_msg = (f"Welcome, {user_name}!\n\nUser ID: `{user_id}`\nStatus: {user_status}{expiry_info}\n"
                   f"Files: {current_files}/{limit_str}\n\n✅ Files need admin approval.\n"
                   f"Send .py/.js/.zip files.\n💰 Use /balance to check coins.")
    main_markup = create_reply_keyboard_main_menu(user_id)
    bot.send_message(chat_id, welcome_msg, reply_markup=main_markup, parse_mode='Markdown')

def _logic_updates_channel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL))
    bot.reply_to(message, "Visit our Updates Channel:", reply_markup=markup)

def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "Bot locked.")
        return
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, f"File limit reached ({current_files}/{limit_str}). Delete files first.")
        return
    bot.reply_to(message, "Send your Python (.py), JS (.js), or ZIP (.zip) file.\n⚠️ All files require admin approval.")

def _logic_check_files(message):
    user_id = message.from_user.id
    files = user_files.get(user_id, [])
    if not files:
        bot.reply_to(message, "Your files:\n\n(No files uploaded yet)")
        return
    response = "📁 **Your Files:**\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(files):
        is_running = is_bot_running(user_id, file_name)
        file_status = get_file_status(user_id, file_name)
        approval_icon = "✅" if file_status['status'] == FILE_STATUS_APPROVED else "⏳" if file_status['status'] == FILE_STATUS_PENDING else "❌"
        status_icon = "🟢" if is_running else "⚪"
        btn_text = f"{approval_icon} {file_name} ({file_type}) - {status_icon}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))
        response += f"{approval_icon} `{file_name}` - {file_status['status'].upper()}\n"
    bot.reply_to(message, response, reply_markup=markup, parse_mode='Markdown')

def _logic_view_pending(message):
    user_id = message.from_user.id
    if user_id not in admin_ids or not check_admin_permission(user_id, 'approve_files'):
        bot.reply_to(message, "Admin permission required.")
        return
    pending = get_all_pending_files()
    if not pending:
        bot.reply_to(message, "✅ No pending files.")
        return
    response = "📋 **Pending Files:**\n\n"
    for idx, (uid, fname, ftype, utime) in enumerate(pending[:20], 1):
        response += f"{idx}. `{fname}` (User: {uid}, Type: {ftype})\n"
    bot.reply_to(message, response, parse_mode='Markdown')

def _logic_bot_speed(message):
    start = time.time()
    msg = bot.reply_to(message, "Testing speed...")
    ping = round((time.time() - start) * 1000, 2)
    status = "Locked" if bot_locked else "Unlocked"
    speed_msg = f"Bot Speed:\nAPI Response: {ping} ms\nBot Status: {status}"
    bot.edit_message_text(speed_msg, message.chat.id, msg.message_id)

def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    bot.reply_to(message, "Click to contact Owner:", reply_markup=markup)

def _logic_uptime(message):
    bot.reply_to(message, f"Uptime: `{get_uptime()}`", parse_mode='Markdown')

def _logic_subscriptions_panel(message):
    user_id = message.from_user.id
    if user_id not in admin_ids or not check_admin_permission(user_id, 'manage_subscriptions'):
        bot.reply_to(message, "Permission denied.")
        return
    bot.reply_to(message, "Subscription Management", reply_markup=create_subscription_menu())

def _logic_statistics(message):
    user_id = message.from_user.id
    total_users = len(active_users)
    total_files = sum(len(f) for f in user_files.values())
    running = sum(1 for k in list(bot_scripts.keys()) if is_bot_running(int(k.split('_')[0]), bot_scripts[k]['file_name']))
    stats = f"📊 Statistics:\nTotal Users: {total_users}\nTotal Files: {total_files}\nRunning Bots: {running}"
    if user_id in admin_ids:
        pending = get_pending_files_count()
        stats += f"\nPending Approvals: {pending}"
    bot.reply_to(message, stats)

def _logic_broadcast_init(message):
    user_id = message.from_user.id
    if user_id not in admin_ids or not check_admin_permission(user_id, 'broadcast'):
        bot.reply_to(message, "Permission denied.")
        return
    msg = bot.reply_to(message, "Send message to broadcast to all active users.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def process_broadcast_message(message):
    user_id = message.from_user.id
    if user_id not in admin_ids or not check_admin_permission(user_id, 'broadcast'):
        bot.reply_to(message, "Not authorized.")
        return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "Broadcast cancelled.")
        return
    broadcast_text = message.text
    if not broadcast_text:
        bot.reply_to(message, "Cannot broadcast empty message.")
        return
    target_count = len(active_users)
    confirm_markup = types.InlineKeyboardMarkup()
    confirm_markup.row(types.InlineKeyboardButton("Confirm & Send", callback_data=f"confirm_broadcast_{message.message_id}"), types.InlineKeyboardButton("Cancel", callback_data="cancel_broadcast"))
    bot.reply_to(message, f"Confirm Broadcast to {target_count} users:\n\n{broadcast_text[:500]}", reply_markup=confirm_markup)

def execute_broadcast(broadcast_text, admin_chat_id):
    sent = 0
    for uid in active_users:
        try:
            bot.send_message(uid, broadcast_text, parse_mode='Markdown')
            sent += 1
            time.sleep(0.1)
        except: pass
    bot.send_message(admin_chat_id, f"Broadcast sent to {sent} users.")

def _logic_toggle_lock_bot(message):
    user_id = message.from_user.id
    if user_id not in admin_ids or not check_admin_permission(user_id, 'lock_bot'):
        bot.reply_to(message, "Permission denied.")
        return
    global bot_locked
    bot_locked = not bot_locked
    status = "locked" if bot_locked else "unlocked"
    bot.reply_to(message, f"Bot {status}.")

def _logic_admin_panel(message):
    user_id = message.from_user.id
    if user_id not in admin_ids:
        bot.reply_to(message, "Admin permissions required.")
        return
    bot.reply_to(message, "Admin Panel", reply_markup=create_admin_panel())

def _logic_run_all_scripts(message):
    user_id = message.from_user.id
    if user_id not in admin_ids or not check_admin_permission(user_id, 'run_all_scripts'):
        bot.reply_to(message, "Permission denied.")
        return
    bot.reply_to(message, "Starting all user scripts...")
    started = 0
    for uid, files in user_files.items():
        for fname, ftype in files:
            if get_file_status(uid, fname)['status'] == FILE_STATUS_APPROVED and not is_bot_running(uid, fname):
                file_path = os.path.join(get_user_folder(uid), fname)
                if os.path.exists(file_path):
                    if ftype == 'py':
                        threading.Thread(target=run_script, args=(file_path, uid, get_user_folder(uid), fname, message)).start()
                    elif ftype == 'js':
                        threading.Thread(target=run_js_script, args=(file_path, uid, get_user_folder(uid), fname, message)).start()
                    started += 1
                    time.sleep(0.5)
    bot.reply_to(message, f"Started {started} scripts.")

def _logic_balance(message):
    user_id = message.from_user.id
    bal = get_balance(user_id)
    bot.reply_to(message, f"💰 Your balance: `{bal}` coins", parse_mode='Markdown')

BUTTON_TEXT_TO_LOGIC = {
    "📢 Updates Channel": _logic_updates_channel,
    "📤 Upload File": _logic_upload_file,
    "📂 Check Files": _logic_check_files,
    "⚡ Bot Speed": _logic_bot_speed,
    "📞 Contact Owner": _logic_contact_owner,
    "📊 Statistics": _logic_statistics,
    "⏱ Uptime": _logic_uptime,
    "💳 Subscriptions": _logic_subscriptions_panel,
    "📢 Broadcast": _logic_broadcast_init,
    "🔒 Lock Bot": _logic_toggle_lock_bot,
    "🟢 Running All Code": _logic_run_all_scripts,
    "👑 Admin Panel": _logic_admin_panel,
    "🤖 MPX Ai": lambda m: bot.reply_to(m, "Use /mpx command"),
    "💰 Balance": _logic_balance
}

@bot.message_handler(func=lambda message: message.text in BUTTON_TEXT_TO_LOGIC)
def handle_button_text(message):
    BUTTON_TEXT_TO_LOGIC[message.text](message)

@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message): _logic_send_welcome(message)

@bot.message_handler(commands=['mpx'])
def handle_mpx_command(message):
    query = message.text.replace('/mpx', '').strip()
    if not query:
        bot.reply_to(message, "Usage: /mpx <question>")
        return
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        headers = {"Authorization": f"Bearer {A4F_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": A4F_MODEL, "messages": [{"role": "user", "content": query}], "temperature": 0.7}
        resp = requests.post(A4F_API_URL, headers=headers, json=payload)
        if resp.status_code == 200:
            answer = resp.json().get('choices', [{}])[0].get('message', {}).get('content', 'No answer')
            bot.reply_to(message, answer[:4000], parse_mode='Markdown')
        else:
            bot.reply_to(message, "API error.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(content_types=['document'])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "Bot locked.")
        return
    doc = message.document
    file_name = doc.file_name
    if not file_name:
        bot.reply_to(message, "No file name.")
        return
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "Only .py, .js, .zip allowed.")
        return
    if doc.file_size > 20*1024*1024:
        bot.reply_to(message, "File too large (max 20MB).")
        return
    try:
        file_info = bot.get_file(doc.file_id)
        file_content = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        if ext == '.zip':
            # handle zip (simplified)
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, file_name)
            with open(zip_path, 'wb') as f: f.write(file_content)
            with zipfile.ZipFile(zip_path, 'r') as zf: zf.extractall(temp_dir)
            py_files = [f for f in os.listdir(temp_dir) if f.endswith('.py')]
            js_files = [f for f in os.listdir(temp_dir) if f.endswith('.js')]
            main_script = None
            file_type = None
            if 'main.py' in py_files: main_script, file_type = 'main.py', 'py'
            elif 'bot.py' in py_files: main_script, file_type = 'bot.py', 'py'
            elif py_files: main_script, file_type = py_files[0], 'py'
            elif js_files: main_script, file_type = js_files[0], 'js'
            if main_script:
                shutil.move(os.path.join(temp_dir, main_script), os.path.join(user_folder, main_script))
                save_user_file(user_id, main_script, file_type)
                save_file_approval(user_id, main_script, file_type, FILE_STATUS_PENDING)
                send_file_for_approval(message, user_id, main_script, file_type)
                bot.reply_to(message, f"✅ ZIP processed. Main script `{main_script}` pending approval.", parse_mode='Markdown')
            shutil.rmtree(temp_dir)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f: f.write(file_content)
            file_type = 'py' if ext == '.py' else 'js'
            save_user_file(user_id, file_name, file_type)
            save_file_approval(user_id, file_name, file_type, FILE_STATUS_PENDING)
            send_file_for_approval(message, user_id, file_name, file_type)
            bot.reply_to(message, f"✅ `{file_name}` uploaded and pending approval.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Upload error: {e}")
        bot.reply_to(message, f"Error: {e}")

# ====================== CALLBACK QUERY HANDLERS ======================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    logger.info(f"Callback: {user_id} -> {data}")
    if bot_locked and user_id not in admin_ids and data not in ['back_to_main','speed','stats','balance','uptime']:
        bot.answer_callback_query(call.id, "Bot locked.", show_alert=True)
        return
    if data == 'upload':
        _logic_upload_file(call.message)
        bot.answer_callback_query(call.id)
    elif data == 'check_files':
        _logic_check_files(call.message)
        bot.answer_callback_query(call.id)
    elif data.startswith('file_'):
        _, owner_id_str, fname = data.split('_', 2)
        owner_id = int(owner_id_str)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Not your file.", show_alert=True)
            return
        is_running = is_bot_running(owner_id, fname)
        markup = create_control_buttons(owner_id, fname, is_running)
        bot.edit_message_text(f"Controls for `{fname}`", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
        bot.answer_callback_query(call.id)
    elif data.startswith('start_'):
        _, owner_id_str, fname = data.split('_', 2)
        owner_id = int(owner_id_str)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        file_status = get_file_status(owner_id, fname)
        if file_status['status'] != FILE_STATUS_APPROVED:
            bot.answer_callback_query(call.id, f"File not approved! Status: {file_status['status']}", show_alert=True)
            return
        if is_bot_running(owner_id, fname):
            bot.answer_callback_query(call.id, "Already running.", show_alert=True)
            return
        file_path = os.path.join(get_user_folder(owner_id), fname)
        ftype = next((ft for (fn, ft) in user_files.get(owner_id, []) if fn == fname), 'py')
        if ftype == 'py':
            threading.Thread(target=run_script, args=(file_path, owner_id, get_user_folder(owner_id), fname, call.message)).start()
        else:
            threading.Thread(target=run_js_script, args=(file_path, owner_id, get_user_folder(owner_id), fname, call.message)).start()
        bot.answer_callback_query(call.id, "Starting script...")
        time.sleep(1)
        is_running = is_bot_running(owner_id, fname)
        markup = create_control_buttons(owner_id, fname, is_running)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif data.startswith('stop_'):
        _, owner_id_str, fname = data.split('_', 2)
        owner_id = int(owner_id_str)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        script_key = f"{owner_id}_{fname}"
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]
            bot.answer_callback_query(call.id, "Stopped.")
        else:
            bot.answer_callback_query(call.id, "Not running.")
        is_running = is_bot_running(owner_id, fname)
        markup = create_control_buttons(owner_id, fname, is_running)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif data.startswith('delete_'):
        _, owner_id_str, fname = data.split('_', 2)
        owner_id = int(owner_id_str)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        script_key = f"{owner_id}_{fname}"
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]
        file_path = os.path.join(get_user_folder(owner_id), fname)
        if os.path.exists(file_path): os.remove(file_path)
        remove_user_file_db(owner_id, fname)
        bot.answer_callback_query(call.id, "Deleted.")
        _logic_check_files(call.message)
    elif data.startswith('logs_'):
        _, owner_id_str, fname = data.split('_', 2)
        owner_id = int(owner_id_str)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        log_path = os.path.join(get_user_folder(owner_id), f"{os.path.splitext(fname)[0]}.log")
        if os.path.exists(log_path):
            with open(log_path, 'r', errors='ignore') as f:
                content = f.read()[-3000:]
            bot.send_message(call.message.chat.id, f"📜 Logs for `{fname}`:\n```\n{content}\n```", parse_mode='Markdown')
        else:
            bot.send_message(call.message.chat.id, "No logs yet.")
        bot.answer_callback_query(call.id)
    elif data == 'speed':
        _logic_bot_speed(call.message)
        bot.answer_callback_query(call.id)
    elif data == 'back_to_main':
        _logic_send_welcome(call.message)
        bot.answer_callback_query(call.id)
    elif data == 'subscription':
        if user_id not in admin_ids or not check_admin_permission(user_id, 'manage_subscriptions'):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        bot.edit_message_text("Subscription Management", call.message.chat.id, call.message.message_id, reply_markup=create_subscription_menu())
        bot.answer_callback_query(call.id)
    elif data == 'stats':
        _logic_statistics(call.message)
        bot.answer_callback_query(call.id)
    elif data == 'lock_bot':
        if user_id not in admin_ids or not check_admin_permission(user_id, 'lock_bot'):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        global bot_locked
        bot_locked = True
        bot.answer_callback_query(call.id, "Bot locked.")
        _logic_send_welcome(call.message)
    elif data == 'unlock_bot':
        if user_id not in admin_ids or not check_admin_permission(user_id, 'lock_bot'):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        bot_locked = False
        bot.answer_callback_query(call.id, "Bot unlocked.")
        _logic_send_welcome(call.message)
    elif data == 'run_all_scripts':
        if user_id not in admin_ids or not check_admin_permission(user_id, 'run_all_scripts'):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        _logic_run_all_scripts(call.message)
        bot.answer_callback_query(call.id)
    elif data == 'admin_panel':
        if user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Admin only.", show_alert=True)
            return
        bot.edit_message_text("Admin Panel", call.message.chat.id, call.message.message_id, reply_markup=create_admin_panel())
        bot.answer_callback_query(call.id)
    elif data == 'add_admin':
        if user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "Owner only.", show_alert=True)
            return
        msg = bot.send_message(call.message.chat.id, "Send user ID to add as admin:")
        bot.register_next_step_handler(msg, process_add_admin_id)
        bot.answer_callback_query(call.id)
    elif data == 'remove_admin':
        if user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "Owner only.", show_alert=True)
            return
        msg = bot.send_message(call.message.chat.id, "Send user ID to remove from admin:")
        bot.register_next_step_handler(msg, process_remove_admin_id)
        bot.answer_callback_query(call.id)
    elif data == 'list_admins':
        if user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Admin only.", show_alert=True)
            return
        admins_str = "\n".join(f"`{aid}`{' (Owner)' if aid==OWNER_ID else ''}" for aid in sorted(admin_ids))
        bot.send_message(call.message.chat.id, f"Admins:\n{admins_str}", parse_mode='Markdown')
        bot.answer_callback_query(call.id)
    elif data == 'add_subscription':
        if user_id not in admin_ids or not check_admin_permission(user_id, 'manage_subscriptions'):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        msg = bot.send_message(call.message.chat.id, "Format: `user_id days`\ne.g. `12345678 30`", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_add_subscription)
        bot.answer_callback_query(call.id)
    elif data == 'remove_subscription':
        if user_id not in admin_ids or not check_admin_permission(user_id, 'manage_subscriptions'):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        msg = bot.send_message(call.message.chat.id, "Send user ID to remove subscription:")
        bot.register_next_step_handler(msg, process_remove_subscription)
        bot.answer_callback_query(call.id)
    elif data == 'check_subscription':
        if user_id not in admin_ids or not check_admin_permission(user_id, 'manage_subscriptions'):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        msg = bot.send_message(call.message.chat.id, "Send user ID to check subscription:")
        bot.register_next_step_handler(msg, process_check_subscription)
        bot.answer_callback_query(call.id)
    elif data == 'view_pending':
        _logic_view_pending(call.message)
        bot.answer_callback_query(call.id)
    elif data == 'balance':
        bal = get_balance(user_id)
        bot.answer_callback_query(call.id, f"Your balance: {bal} coins", show_alert=True)
    elif data == 'mpx_ai':
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Use /mpx <question>")
    elif data == 'uptime':
        bot.answer_callback_query(call.id, f"Uptime: {get_uptime()}", show_alert=True)
    elif data == 'admin_perms_panel':
        if user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "Owner only.", show_alert=True)
            return
        bot.edit_message_text("Select admin to edit permissions:", call.message.chat.id, call.message.message_id, reply_markup=create_admin_list_for_perms())
        bot.answer_callback_query(call.id)
    elif data.startswith('admin_perm_edit_'):
        if user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "Owner only.", show_alert=True)
            return
        target_admin = int(data.split('_')[-1])
        bot.edit_message_text(f"Editing permissions for admin {target_admin}", call.message.chat.id, call.message.message_id, reply_markup=create_admin_permissions_panel(target_admin))
        bot.answer_callback_query(call.id)
    elif data.startswith('toggle_perm_'):
        if user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "Owner only.", show_alert=True)
            return
        parts = data.split('_')
        target_admin = int(parts[2])
        perm = '_'.join(parts[3:])
        current = get_admin_permissions(target_admin).get(perm, False)
        new_val = not current
        update_admin_permission(target_admin, perm, new_val)
        bot.answer_callback_query(call.id, f"Permission {perm} set to {new_val}")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_admin_permissions_panel(target_admin))
    elif data == 'admin_perms_list':
        if user_id != OWNER_ID:
            bot.answer_callback_query(call.id, "Owner only.", show_alert=True)
            return
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_admin_list_for_perms())
        bot.answer_callback_query(call.id)
    elif data == 'banking_panel':
        if user_id != OWNER_ID and not check_admin_permission(user_id, 'banking'):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        bot.edit_message_text("Banking Operations", call.message.chat.id, call.message.message_id, reply_markup=create_banking_panel())
        bot.answer_callback_query(call.id)
    elif data == 'add_balance':
        if user_id != OWNER_ID and not check_admin_permission(user_id, 'banking'):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        msg = bot.send_message(call.message.chat.id, "Format: `user_id amount`\ne.g. `12345678 100`", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_add_balance)
        bot.answer_callback_query(call.id)
    elif data == 'deduct_balance':
        if user_id != OWNER_ID and not check_admin_permission(user_id, 'banking'):
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        msg = bot.send_message(call.message.chat.id, "Format: `user_id amount`\ne.g. `12345678 50`", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_deduct_balance)
        bot.answer_callback_query(call.id)
    elif data.startswith('confirm_broadcast_'):
        if user_id not in admin_ids or not check_admin_permission(user_id, 'broadcast'):
            bot.answer_callback_query(call.id, "Not authorized.", show_alert=True)
            return
        original_msg = call.message.reply_to_message
        if original_msg and original_msg.text:
            broadcast_text = original_msg.text.replace("Confirm Broadcast", "").split("\n\n")[-1].strip()
            threading.Thread(target=execute_broadcast, args=(broadcast_text, call.message.chat.id)).start()
            bot.answer_callback_query(call.id, "Broadcasting...")
            bot.delete_message(call.message.chat.id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "Invalid broadcast message.", show_alert=True)
    elif data == 'cancel_broadcast':
        bot.answer_callback_query(call.id, "Cancelled.")
        bot.delete_message(call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "Unknown action")

def process_add_admin_id(message):
    if message.from_user.id != OWNER_ID: return
    try:
        new_id = int(message.text.strip())
        if new_id in admin_ids:
            bot.reply_to(message, "Already admin.")
            return
        add_admin_db(new_id)
        bot.reply_to(message, f"Admin {new_id} added.")
    except: bot.reply_to(message, "Invalid ID.")

def process_remove_admin_id(message):
    if message.from_user.id != OWNER_ID: return
    try:
        rem_id = int(message.text.strip())
        if rem_id == OWNER_ID:
            bot.reply_to(message, "Cannot remove owner.")
            return
        if remove_admin_db(rem_id):
            bot.reply_to(message, f"Admin {rem_id} removed.")
        else:
            bot.reply_to(message, "Not an admin or error.")
    except: bot.reply_to(message, "Invalid ID.")

def process_add_subscription(message):
    user_id = message.from_user.id
    if user_id not in admin_ids or not check_admin_permission(user_id, 'manage_subscriptions'): return
    try:
        parts = message.text.split()
        uid = int(parts[0])
        days = int(parts[1])
        new_expiry = datetime.now() + timedelta(days=days)
        save_subscription(uid, new_expiry)
        bot.reply_to(message, f"Subscription added for {uid}, expires {new_expiry.strftime('%Y-%m-%d')}")
    except: bot.reply_to(message, "Invalid format. Use: user_id days")

def process_remove_subscription(message):
    user_id = message.from_user.id
    if user_id not in admin_ids or not check_admin_permission(user_id, 'manage_subscriptions'): return
    try:
        uid = int(message.text.strip())
        if uid in user_subscriptions:
            remove_subscription_db(uid)
            bot.reply_to(message, f"Subscription removed for {uid}")
        else:
            bot.reply_to(message, "No active subscription.")
    except: bot.reply_to(message, "Invalid ID.")

def process_check_subscription(message):
    user_id = message.from_user.id
    if user_id not in admin_ids or not check_admin_permission(user_id, 'manage_subscriptions'): return
    try:
        uid = int(message.text.strip())
        if uid in user_subscriptions:
            exp = user_subscriptions[uid]['expiry']
            bot.reply_to(message, f"User {uid} subscription expires: {exp.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            bot.reply_to(message, f"No active subscription for {uid}")
    except: bot.reply_to(message, "Invalid ID.")

def process_add_balance(message):
    admin_id = message.from_user.id
    if admin_id != OWNER_ID and not check_admin_permission(admin_id, 'banking'): return
    try:
        parts = message.text.split()
        uid = int(parts[0])
        amt = int(parts[1])
        new_bal = add_balance(uid, amt)
        bot.reply_to(message, f"Added {amt} to {uid}. New balance: {new_bal}")
    except: bot.reply_to(message, "Invalid. Use: user_id amount")

def process_deduct_balance(message):
    admin_id = message.from_user.id
    if admin_id != OWNER_ID and not check_admin_permission(admin_id, 'banking'): return
    try:
        parts = message.text.split()
        uid = int(parts[0])
        amt = int(parts[1])
        new_bal = deduct_balance(uid, amt)
        if new_bal is None:
            bot.reply_to(message, "Insufficient balance.")
        else:
            bot.reply_to(message, f"Deducted {amt} from {uid}. New balance: {new_bal}")
    except: bot.reply_to(message, "Invalid. Use: user_id amount")

# ====================== APPROVAL CALLBACKS ======================
@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def approve_callback(call):
    admin_id = call.from_user.id
    if admin_id not in admin_ids or not check_admin_permission(admin_id, 'approve_files'):
        bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
        return
    _, uid_str, fname = call.data.split('_', 2)
    uid = int(uid_str)
    if update_file_status(uid, fname, FILE_STATUS_APPROVED, admin_id):
        try:
            bot.send_message(uid, f"✅ Your file `{fname}` has been approved! You can now run it.", parse_mode='Markdown')
        except: pass
        bot.answer_callback_query(call.id, "Approved.")
        bot.edit_message_text(f"✅ Approved: {fname}", call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "Error.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def reject_callback(call):
    admin_id = call.from_user.id
    if admin_id not in admin_ids or not check_admin_permission(admin_id, 'approve_files'):
        bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
        return
    _, uid_str, fname = call.data.split('_', 2)
    uid = int(uid_str)
    if update_file_status(uid, fname, FILE_STATUS_REJECTED, admin_id):
        try:
            bot.send_message(uid, f"❌ Your file `{fname}` was rejected by admin.", parse_mode='Markdown')
        except: pass
        bot.answer_callback_query(call.id, "Rejected.")
        bot.edit_message_text(f"❌ Rejected: {fname}", call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "Error.")

# ====================== FLASK & POLLING ======================
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    logging.info("✅ Flask Keep-Alive started")

def cleanup():
    logger.warning("Shutting down, killing child processes...")
    for script_key in list(bot_scripts.keys()):
        kill_process_tree(bot_scripts[script_key])
    logger.info("Cleanup done.")
atexit.register(cleanup)

if __name__ == '__main__':
    keep_alive()
    logger.info("Bot starting...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(10)