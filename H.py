# H.py - COMPLETE FIXED VERSION FOR RENDER
# Added: Admin permission toggles (on/off) + Processing animation

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

# Permission settings (from DB later)
PERMISSION_DEFAULTS = {
    'user_file_forward': True,      # Forward uploaded file to admins?
    'auto_approve': False,          # NEVER auto-approve (force manual)
    'broadcast_enabled': True,
    'admin_add_remove': True,
    'subscription_manage': True,
    'bot_lock_enabled': True,
    'run_all_scripts': True
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

FILE_STATUS_PENDING = "pending"
FILE_STATUS_APPROVED = "approved"
FILE_STATUS_REJECTED = "rejected"

COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel", "⏱ Uptime"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["📞 Contact Owner", "🤖 MPX Ai"]
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel", "/ping"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💳 Subscriptions", "📢 Broadcast"],
    ["🔒 Lock Bot", "🟢 Running All Code"],
    ["👑 Admin Panel", "📞 Contact Owner"],
    ["🤖 MPX Ai", "⏱ Uptime"],
]

def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS file_approvals
                     (user_id INTEGER, file_name TEXT, status TEXT, 
                      reviewed_by INTEGER, review_time TEXT, file_type TEXT,
                      uploaded_time TEXT, message_id INTEGER,
                      PRIMARY KEY (user_id, file_name))''')
        # NEW: admin permissions table
        c.execute('''CREATE TABLE IF NOT EXISTS admin_settings
                     (setting_key TEXT PRIMARY KEY, setting_value INTEGER)''')
        conn.commit()
        
        # Insert default permission values if not exist
        for key, default in PERMISSION_DEFAULTS.items():
            c.execute('INSERT OR IGNORE INTO admin_settings (setting_key, setting_value) VALUES (?, ?)',
                      (key, 1 if default else 0))
        conn.commit()
        
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

# ---------- Admin permission helpers ----------
def get_admin_setting(key):
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT setting_value FROM admin_settings WHERE setting_key = ?', (key,))
        row = c.fetchone()
        conn.close()
        if row:
            return bool(row[0])
        return PERMISSION_DEFAULTS.get(key, False)
    except:
        return PERMISSION_DEFAULTS.get(key, False)

def set_admin_setting(key, value):
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('REPLACE INTO admin_settings (setting_key, setting_value) VALUES (?, ?)',
                  (key, 1 if value else 0))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to set setting {key}: {e}")
        return False

def toggle_admin_setting(key):
    current = get_admin_setting(key)
    new = not current
    set_admin_setting(key, new)
    return new

# ---------- Animation helper ----------
def show_processing_animation(chat_id, text="Processing"):
    msg = bot.send_message(chat_id, f"{text}   ")
    frames = ["   ", ".  ", ".. ", "..."]
    def animate():
        for i in range(12):
            frame = frames[i % len(frames)]
            try:
                bot.edit_message_text(f"{text}{frame}", chat_id, msg.message_id)
            except:
                pass
            time.sleep(0.5)
        try:
            bot.edit_message_text(f"{text} ✓ Done!", chat_id, msg.message_id)
        except:
            pass
    threading.Thread(target=animate).start()
    return msg.message_id

# ---------- DB helper functions (unchanged but keep) ----------
DB_LOCK = threading.Lock()

def save_file_approval(user_id, file_name, file_type, status=FILE_STATUS_PENDING, reviewed_by=None, message_id=None):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            uploaded_time = datetime.now().isoformat()
            review_time = datetime.now().isoformat() if reviewed_by else None
            c.execute('''INSERT OR REPLACE INTO file_approvals 
                        (user_id, file_name, file_type, status, reviewed_by, review_time, uploaded_time, message_id) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
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
            c.execute('''SELECT status, reviewed_by, review_time, file_type 
                        FROM file_approvals WHERE user_id=? AND file_name=?''',
                     (user_id, file_name))
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
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            review_time = datetime.now().isoformat()
            c.execute('''UPDATE file_approvals 
                        SET status=?, reviewed_by=?, review_time=?
                        WHERE user_id=? AND file_name=?''',
                     (status, admin_id, review_time, user_id, file_name))
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
            c.execute('''SELECT user_id, file_name, file_type, uploaded_time 
                        FROM file_approvals WHERE status=? 
                        ORDER BY uploaded_time DESC''', (FILE_STATUS_PENDING,))
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
    file_info = (
        f"📄 **NEW FILE FOR APPROVAL**\n\n"
        f"👤 **User:** {user.first_name}\n"
        f"📛 **Username:** @{user.username or 'N/A'}\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"📁 **File:** `{file_name}`\n"
        f"📊 **Type:** {file_type}\n"
        f"🕐 **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"**Choose action:**"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f'approve_{user_id}_{file_name}'),
        types.InlineKeyboardButton("❌ Reject", callback_data=f'reject_{user_id}_{file_name}')
    )
    markup.add(types.InlineKeyboardButton("📋 View All Pending", callback_data='view_pending'))
    
    # Check if forwarding is allowed via admin permission
    if get_admin_setting('user_file_forward'):
        for admin_id in admin_ids:
            try:
                bot.forward_message(admin_id, message.chat.id, message.message_id)
                sent_msg = bot.send_message(admin_id, file_info, reply_markup=markup, parse_mode='Markdown')
                save_file_approval(user_id, file_name, file_type, FILE_STATUS_PENDING, None, sent_msg.message_id)
            except Exception as e:
                logger.error(f"Failed to send file for approval to admin {admin_id}: {e}")
    else:
        # Still save for manual admin check later
        save_file_approval(user_id, file_name, file_type, FILE_STATUS_PENDING)
        bot.send_message(OWNER_ID, f"⚠️ File forward disabled! File from {user_id}: {file_name} needs manual approval via /pending", parse_mode='Markdown')

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
                    try:
                        script_info['log_file'].close()
                    except: pass
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                try: script_info['log_file'].close()
                except: pass
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            return False
        except Exception as e:
            logger.error(f"Error checking process status: {e}")
            return False
    return False

def kill_process_tree(process_info):
    pid = None
    script_key = process_info.get('script_key', 'N/A')
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
                        try:
                            child.terminate()
                        except: pass
                    gone, alive = psutil.wait_procs(children, timeout=1)
                    for p in alive:
                        try: p.kill()
                        except: pass
                    try:
                        parent.terminate()
                        try: parent.wait(timeout=1)
                        except: parent.kill()
                    except: pass
                except: pass
    except Exception as e:
        logger.error(f"Unexpected error killing process: {e}")

TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI', 'telegram': 'python-telegram-bot', 'aiogram': 'aiogram',
    'pyrogram': 'pyrogram', 'telethon': 'telethon', 'flask': 'Flask', 'requests': 'requests',
    'psutil': 'psutil', 'sqlite3': None, 'datetime': None, 'os': None, 'sys': None
}

def attempt_install_pip(module_name, message):
    package_name = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    if package_name is None:
        return False
    try:
        bot.reply_to(message, f"Module `{module_name}` not found. Installing `{package_name}`...", parse_mode='Markdown')
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', package_name], capture_output=True, text=True)
        if result.returncode == 0:
            bot.reply_to(message, f"Package `{package_name}` installed.", parse_mode='Markdown')
            return True
        else:
            bot.reply_to(message, f"Failed to install `{package_name}`.", parse_mode='Markdown')
            return False
    except Exception as e:
        bot.reply_to(message, f"Install error: {e}")
        return False

def attempt_install_npm(module_name, user_folder, message):
    try:
        bot.reply_to(message, f"Node package `{module_name}` not found. Installing locally...", parse_mode='Markdown')
        result = subprocess.run(['npm', 'install', module_name], capture_output=True, text=True, cwd=user_folder)
        if result.returncode == 0:
            bot.reply_to(message, f"Node package `{module_name}` installed.", parse_mode='Markdown')
            return True
        else:
            bot.reply_to(message, f"Failed to install `{module_name}`.", parse_mode='Markdown')
            return False
    except:
        bot.reply_to(message, "npm not found.")
        return False

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    file_status = get_file_status(script_owner_id, file_name)
    if file_status['status'] != FILE_STATUS_APPROVED:
        bot.reply_to(message_obj_for_reply, f"❌ File `{file_name}` not approved yet! Status: {file_status['status']}", parse_mode='Markdown')
        return
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"Failed to run '{file_name}' after {max_attempts} attempts.")
        return
    script_key = f"{script_owner_id}_{file_name}"
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"Error: Script '{file_name}' not found!")
            remove_user_file_db(script_owner_id, file_name)
            return
        if attempt == 1:
            check_proc = subprocess.Popen([sys.executable, script_path], cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                stdout, stderr = check_proc.communicate(timeout=5)
                if check_proc.returncode != 0 and stderr:
                    match = re.search(r"ModuleNotFoundError: No module named '(.+?)'", stderr)
                    if match:
                        module_name = match.group(1)
                        if attempt_install_pip(module_name, message_obj_for_reply):
                            time.sleep(2)
                            threading.Thread(target=run_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt+1)).start()
                            return
                        else:
                            bot.reply_to(message_obj_for_reply, f"Install failed. Cannot run '{file_name}'.")
                            return
            except subprocess.TimeoutExpired:
                check_proc.kill()
                check_proc.communicate()
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        process = subprocess.Popen([sys.executable, script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.PIPE)
        bot_scripts[script_key] = {'process': process, 'log_file': log_file, 'file_name': file_name, 'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id, 'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'py', 'script_key': script_key}
        bot.reply_to(message_obj_for_reply, f"Python script '{file_name}' started! (PID: {process.pid})")
    except Exception as e:
        bot.reply_to(message_obj_for_reply, f"Error starting script: {e}")

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    file_status = get_file_status(script_owner_id, file_name)
    if file_status['status'] != FILE_STATUS_APPROVED:
        bot.reply_to(message_obj_for_reply, f"❌ File `{file_name}` not approved yet!", parse_mode='Markdown')
        return
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"Failed to run '{file_name}' after {max_attempts} attempts.")
        return
    script_key = f"{script_owner_id}_{file_name}"
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"Error: Script '{file_name}' not found!")
            remove_user_file_db(script_owner_id, file_name)
            return
        if attempt == 1:
            check_proc = subprocess.Popen(['node', script_path], cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                stdout, stderr = check_proc.communicate(timeout=5)
                if check_proc.returncode != 0 and stderr:
                    match = re.search(r"Cannot find module '(.+?)'", stderr)
                    if match:
                        module_name = match.group(1)
                        if attempt_install_npm(module_name, user_folder, message_obj_for_reply):
                            time.sleep(2)
                            threading.Thread(target=run_js_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt+1)).start()
                            return
                        else:
                            bot.reply_to(message_obj_for_reply, f"NPM install failed. Cannot run '{file_name}'.")
                            return
            except subprocess.TimeoutExpired:
                check_proc.kill()
                check_proc.communicate()
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        process = subprocess.Popen(['node', script_path], cwd=user_folder, stdout=log_file, stderr=log_file, stdin=subprocess.PIPE)
        bot_scripts[script_key] = {'process': process, 'log_file': log_file, 'file_name': file_name, 'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id, 'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'js', 'script_key': script_key}
        bot.reply_to(message_obj_for_reply, f"JS script '{file_name}' started! (PID: {process.pid})")
    except Exception as e:
        bot.reply_to(message_obj_for_reply, f"Error starting JS: {e}")

def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files VALUES (?, ?, ?)', (user_id, file_name, file_type))
            conn.commit()
            if user_id not in user_files: user_files[user_id] = []
            user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
        finally:
            conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id=? AND file_name=?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
                if not user_files[user_id]: del user_files[user_id]
        finally:
            conn.close()

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
            conn.commit()
        finally:
            conn.close()

def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            expiry_str = expiry.isoformat()
            c.execute('INSERT OR REPLACE INTO subscriptions VALUES (?, ?)', (user_id, expiry_str))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry}
        finally:
            conn.close()

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id=?', (user_id,))
            conn.commit()
            if user_id in user_subscriptions: del user_subscriptions[user_id]
        finally:
            conn.close()

def add_admin_db(admin_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (admin_id,))
            conn.commit()
            admin_ids.add(admin_id)
        finally:
            conn.close()

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID: return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM admins WHERE user_id=?', (admin_id,))
            conn.commit()
            removed = c.rowcount > 0
            if removed: admin_ids.discard(admin_id)
            return removed
        finally:
            conn.close()

# ---------- Permission management menu ----------
def create_permissions_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    status_forward = "✅" if get_admin_setting('user_file_forward') else "❌"
    status_broadcast = "✅" if get_admin_setting('broadcast_enabled') else "❌"
    status_admin_add = "✅" if get_admin_setting('admin_add_remove') else "❌"
    status_sub_manage = "✅" if get_admin_setting('subscription_manage') else "❌"
    status_lock = "✅" if get_admin_setting('bot_lock_enabled') else "❌"
    status_runall = "✅" if get_admin_setting('run_all_scripts') else "❌"
    
    markup.add(
        types.InlineKeyboardButton(f"{status_forward} Forward Files to Admins", callback_data='perm_forward'),
        types.InlineKeyboardButton(f"{status_broadcast} Broadcast Messages", callback_data='perm_broadcast'),
        types.InlineKeyboardButton(f"{status_admin_add} Add/Remove Admins", callback_data='perm_admin_add'),
        types.InlineKeyboardButton(f"{status_sub_manage} Subscription Management", callback_data='perm_sub_manage'),
        types.InlineKeyboardButton(f"{status_lock} Bot Lock Feature", callback_data='perm_lock'),
        types.InlineKeyboardButton(f"{status_runall} Run All Scripts", callback_data='perm_runall')
    )
    markup.add(types.InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel'))
    return markup

def handle_permissions_callback(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "Admin only", show_alert=True)
        return
    data = call.data
    if data == 'perm_forward':
        new_val = toggle_admin_setting('user_file_forward')
        bot.answer_callback_query(call.id, f"File forward {'enabled' if new_val else 'disabled'}")
    elif data == 'perm_broadcast':
        new_val = toggle_admin_setting('broadcast_enabled')
        bot.answer_callback_query(call.id, f"Broadcast {'enabled' if new_val else 'disabled'}")
    elif data == 'perm_admin_add':
        new_val = toggle_admin_setting('admin_add_remove')
        bot.answer_callback_query(call.id, f"Admin add/remove {'enabled' if new_val else 'disabled'}")
    elif data == 'perm_sub_manage':
        new_val = toggle_admin_setting('subscription_manage')
        bot.answer_callback_query(call.id, f"Subscription management {'enabled' if new_val else 'disabled'}")
    elif data == 'perm_lock':
        new_val = toggle_admin_setting('bot_lock_enabled')
        bot.answer_callback_query(call.id, f"Bot lock feature {'enabled' if new_val else 'disabled'}")
    elif data == 'perm_runall':
        new_val = toggle_admin_setting('run_all_scripts')
        bot.answer_callback_query(call.id, f"Run all scripts {'enabled' if new_val else 'disabled'}")
    # Refresh menu
    bot.edit_message_text("⚙️ Admin Permission Settings\nToggle any feature:", call.message.chat.id, call.message.message_id, reply_markup=create_permissions_menu())

# ---------- Menu helpers ----------
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL),
        types.InlineKeyboardButton('📤 Upload File', callback_data='upload'),
        types.InlineKeyboardButton('📂 Check Files', callback_data='check_files'),
        types.InlineKeyboardButton('⚡ Bot Speed', callback_data='speed'),
        types.InlineKeyboardButton('📊 Statistics', callback_data='stats'),
        types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'),
        types.InlineKeyboardButton('🤖 MPX AI', callback_data='mpx_ai')
    ]
    if user_id in admin_ids:
        pending_count = get_pending_files_count()
        pending_text = f"📋 Pending Files ({pending_count})" if pending_count > 0 else "📋 Pending Files"
        admin_buttons = [
            types.InlineKeyboardButton(pending_text, callback_data='view_pending'),
            types.InlineKeyboardButton('💳 Subscriptions', callback_data='subscription'),
            types.InlineKeyboardButton('📢 Broadcast', callback_data='broadcast'),
            types.InlineKeyboardButton('🔒 Lock Bot' if not bot_locked else '🔓 Unlock Bot', callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
            types.InlineKeyboardButton('👑 Admin Panel', callback_data='admin_panel'),
            types.InlineKeyboardButton('🟢 Run All User Scripts', callback_data='run_all_scripts'),
            types.InlineKeyboardButton('⚙️ Permission Settings', callback_data='permissions_menu')
        ]
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3], admin_buttons[0])
        markup.add(buttons[4], admin_buttons[1])
        markup.add(admin_buttons[2], admin_buttons[4])
        markup.add(admin_buttons[3], admin_buttons[6])
        markup.add(admin_buttons[5])
        markup.add(buttons[5], buttons[6])
    else:
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3])
        markup.add(buttons[4])
        markup.add(buttons[5], buttons[6])
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
        markup.row(types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{script_owner_id}_{file_name}'),
                   types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{script_owner_id}_{file_name}'))
        markup.row(types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'),
                   types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}'))
    else:
        markup.row(types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{script_owner_id}_{file_name}'),
                   types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'))
        markup.row(types.InlineKeyboardButton("📜 View Logs", callback_data=f'logs_{script_owner_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton(f"Status: {status_text}", callback_data=f'status_{script_owner_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("🔙 Back to Files", callback_data='check_files'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    if get_admin_setting('admin_add_remove'):
        markup.row(types.InlineKeyboardButton('➕ Add Admin', callback_data='add_admin'),
                   types.InlineKeyboardButton('➖ Remove Admin', callback_data='remove_admin'))
    markup.row(types.InlineKeyboardButton('📋 List Admins', callback_data='list_admins'),
               types.InlineKeyboardButton('📋 Pending Files', callback_data='view_pending'))
    markup.row(types.InlineKeyboardButton('⚙️ Permission Settings', callback_data='permissions_menu'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    if get_admin_setting('subscription_manage'):
        markup.row(types.InlineKeyboardButton('➕ Add Subscription', callback_data='add_subscription'),
                   types.InlineKeyboardButton('➖ Remove Subscription', callback_data='remove_subscription'))
    markup.row(types.InlineKeyboardButton('🔍 Check Subscription', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

# ---------- Logic functions (shortened for brevity but complete) ----------
def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    user_username = message.from_user.username
    if bot_locked and get_admin_setting('bot_lock_enabled') and user_id not in admin_ids:
        bot.send_message(chat_id, "Bot locked by admin. Try later.")
        return
    if user_id not in active_users:
        add_active_user(user_id)
        try:
            owner_notification = f"New user!\nName: {user_name}\nUser: @{user_username or 'N/A'}\nID: `{user_id}`"
            bot.send_message(OWNER_ID, owner_notification, parse_mode='Markdown')
        except: pass
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    user_status = "Owner" if user_id == OWNER_ID else "Admin" if user_id in admin_ids else "Premium" if user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now() else "Free User"
    welcome_msg = f"Welcome, {user_name}!\nUser ID: `{user_id}`\nStatus: {user_status}\nFiles: {current_files}/{limit_str}\n\n✅ Files need admin approval.\nSend .py .js or .zip"
    bot.send_message(chat_id, welcome_msg, reply_markup=create_reply_keyboard_main_menu(user_id), parse_mode='Markdown')

def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and get_admin_setting('bot_lock_enabled') and user_id not in admin_ids:
        bot.reply_to(message, "Bot locked.")
        return
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        bot.reply_to(message, f"File limit reached ({current_files}/{file_limit}).")
        return
    bot.reply_to(message, "Send .py, .js or .zip file. All files need admin approval.")

def _logic_check_files(message):
    user_id = message.from_user.id
    files = user_files.get(user_id, [])
    if not files:
        bot.reply_to(message, "No files uploaded.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for fname, ftype in sorted(files):
        is_running = is_bot_running(user_id, fname)
        status = get_file_status(user_id, fname)['status']
        icon = "✅" if status == "approved" else "⏳" if status == "pending" else "❌"
        markup.add(types.InlineKeyboardButton(f"{icon} {fname} ({ftype}) - {'🟢' if is_running else '⚪'}", callback_data=f'file_{user_id}_{fname}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    bot.reply_to(message, "📁 Your files:", reply_markup=markup)

def _logic_bot_speed(message):
    start = time.time()
    msg = bot.reply_to(message, "Testing speed...")
    latency = round((time.time() - start) * 1000, 2)
    bot.edit_message_text(f"Speed: {latency} ms\nStatus: {'Locked' if bot_locked else 'Unlocked'}", message.chat.id, msg.message_id)

def _logic_statistics(message):
    total_users = len(active_users)
    total_files = sum(len(f) for f in user_files.values())
    running = sum(1 for uid,fname in [(uid,fn) for uid,flist in user_files.items() for fn,_ in flist] if is_bot_running(uid, fname))
    bot.reply_to(message, f"📊 Stats\nUsers: {total_users}\nFiles: {total_files}\nRunning: {running}")

def _logic_uptime(message):
    bot.reply_to(message, f"Uptime: {get_uptime()}")

def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    bot.reply_to(message, "Click to contact:", reply_markup=markup)

def _logic_updates_channel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('Updates Channel', url=UPDATE_CHANNEL))
    bot.reply_to(message, "Join updates:", reply_markup=markup)

def _logic_view_pending(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "Admin only.")
        return
    pending = get_all_pending_files()
    if not pending:
        bot.reply_to(message, "No pending files.")
        return
    text = "📋 Pending files:\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, fname, ftype, _ in pending[:20]:
        markup.add(types.InlineKeyboardButton(f"{uid} - {fname}", callback_data=f'review_{uid}_{fname}'))
    markup.add(types.InlineKeyboardButton("Refresh", callback_data='view_pending'), types.InlineKeyboardButton("Back", callback_data='back_to_main'))
    bot.reply_to(message, text, reply_markup=markup)

def _logic_subscriptions_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "Admin only.")
        return
    bot.reply_to(message, "Subscription management", reply_markup=create_subscription_menu())

def _logic_broadcast_init(message):
    if message.from_user.id not in admin_ids or not get_admin_setting('broadcast_enabled'):
        bot.reply_to(message, "Not allowed.")
        return
    msg = bot.reply_to(message, "Send message to broadcast.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def process_broadcast_message(message):
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    content = message.text
    if not content:
        bot.reply_to(message, "Text only broadcast.")
        return
    confirm_markup = types.InlineKeyboardMarkup()
    confirm_markup.row(types.InlineKeyboardButton("Confirm", callback_data=f"confirm_broadcast_{message.message_id}"),
                       types.InlineKeyboardButton("Cancel", callback_data="cancel_broadcast"))
    bot.reply_to(message, f"Confirm broadcast to {len(active_users)} users:\n\n{content[:200]}", reply_markup=confirm_markup)

def handle_confirm_broadcast(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "No permission")
        return
    original = call.message.reply_to_message
    if not original or not original.text:
        bot.edit_message_text("Error: no content", call.message.chat.id, call.message.message_id)
        return
    content = original.text
    bot.edit_message_text("Broadcasting...", call.message.chat.id, call.message.message_id)
    sent = 0
    for uid in list(active_users):
        try:
            bot.send_message(uid, content)
            sent += 1
            time.sleep(0.05)
        except:
            pass
    bot.edit_message_text(f"Broadcast done. Sent to {sent} users.", call.message.chat.id, call.message.message_id)

def handle_cancel_broadcast(call):
    bot.edit_message_text("Broadcast cancelled.", call.message.chat.id, call.message.message_id)

def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids or not get_admin_setting('bot_lock_enabled'):
        bot.reply_to(message, "Not allowed.")
        return
    global bot_locked
    bot_locked = not bot_locked
    bot.reply_to(message, f"Bot {'locked' if bot_locked else 'unlocked'}.")

def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "Admin only.")
        return
    bot.reply_to(message, "Admin Panel:", reply_markup=create_admin_panel())

def _logic_run_all_scripts(message):
    if message.from_user.id not in admin_ids or not get_admin_setting('run_all_scripts'):
        bot.reply_to(message, "Not allowed.")
        return
    bot.reply_to(message, "Starting all approved scripts...")
    started = 0
    for uid, flist in user_files.items():
        for fname, ftype in flist:
            if get_file_status(uid, fname)['status'] == FILE_STATUS_APPROVED and not is_bot_running(uid, fname):
                folder = get_user_folder(uid)
                fpath = os.path.join(folder, fname)
                if os.path.exists(fpath):
                    if ftype == 'py':
                        threading.Thread(target=run_script, args=(fpath, uid, folder, fname, message)).start()
                    elif ftype == 'js':
                        threading.Thread(target=run_js_script, args=(fpath, uid, folder, fname, message)).start()
                    started += 1
                    time.sleep(0.5)
    bot.reply_to(message, f"Started {started} scripts.")

# ---------- File upload handlers with animation ----------
def handle_zip_file(downloaded_content, zip_name, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, zip_name)
    with open(zip_path, 'wb') as f:
        f.write(downloaded_content)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(temp_dir)
    # detect main script
    files = os.listdir(temp_dir)
    py_files = [f for f in files if f.endswith('.py')]
    js_files = [f for f in files if f.endswith('.js')]
    main = None
    ftype = None
    if 'main.py' in py_files:
        main = 'main.py'; ftype = 'py'
    elif 'bot.py' in py_files:
        main = 'bot.py'; ftype = 'py'
    elif py_files:
        main = py_files[0]; ftype = 'py'
    elif 'index.js' in js_files:
        main = 'index.js'; ftype = 'js'
    elif js_files:
        main = js_files[0]; ftype = 'js'
    if not main:
        bot.reply_to(message, "No .py or .js found in zip.")
        shutil.rmtree(temp_dir)
        return
    # move files
    for item in os.listdir(temp_dir):
        src = os.path.join(temp_dir, item)
        dst = os.path.join(user_folder, item)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        elif os.path.exists(dst):
            os.remove(dst)
        shutil.move(src, dst)
    shutil.rmtree(temp_dir)
    save_user_file(user_id, main, ftype)
    save_file_approval(user_id, main, ftype, FILE_STATUS_PENDING)
    send_file_for_approval(message, user_id, main, ftype)
    bot.reply_to(message, f"✅ Extracted and uploaded `{main}`. Waiting admin approval.", parse_mode='Markdown')

def handle_py_file(file_path, user_id, user_folder, file_name, message):
    save_user_file(user_id, file_name, 'py')
    save_file_approval(user_id, file_name, 'py', FILE_STATUS_PENDING)
    send_file_for_approval(message, user_id, file_name, 'py')
    bot.reply_to(message, f"✅ Python file `{file_name}` uploaded. Pending approval.", parse_mode='Markdown')

def handle_js_file(file_path, user_id, user_folder, file_name, message):
    save_user_file(user_id, file_name, 'js')
    save_file_approval(user_id, file_name, 'js', FILE_STATUS_PENDING)
    send_file_for_approval(message, user_id, file_name, 'js')
    bot.reply_to(message, f"✅ JS file `{file_name}` uploaded. Pending approval.", parse_mode='Markdown')

@bot.message_handler(commands=['start', 'help'])
def start_handler(message):
    _logic_send_welcome(message)

@bot.message_handler(commands=['mpx'])
def mpx_handler(message):
    user_id = message.from_user.id
    if bot_locked and get_admin_setting('bot_lock_enabled') and user_id not in admin_ids:
        bot.reply_to(message, "Bot locked.")
        return
    query = message.text.split(' ', 1)
    if len(query) < 2:
        bot.reply_to(message, "Usage: /mpx your question")
        return
    show_processing_animation(message.chat.id, "Asking MPX AI")
    try:
        headers = {"Authorization": f"Bearer {A4F_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": A4F_MODEL, "messages": [{"role": "user", "content": query[1]}]}
        resp = requests.post(A4F_API_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            answer = resp.json().get('choices', [{}])[0].get('message', {}).get('content', "No response")
            bot.reply_to(message, answer[:4000])
        else:
            bot.reply_to(message, "API error.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(content_types=['document'])
def handle_doc(message):
    user_id = message.from_user.id
    if bot_locked and get_admin_setting('bot_lock_enabled') and user_id not in admin_ids:
        bot.reply_to(message, "Bot locked.")
        return
    file_limit = get_user_file_limit(user_id)
    current = get_user_file_count(user_id)
    if current >= file_limit:
        bot.reply_to(message, f"Limit reached ({current}/{file_limit}).")
        return
    doc = message.document
    fname = doc.file_name
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "Only .py .js .zip allowed.")
        return
    show_processing_animation(message.chat.id, f"Downloading {fname}")
    try:
        file_info = bot.get_file(doc.file_id)
        content = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        if ext == '.zip':
            handle_zip_file(content, fname, message)
        else:
            fpath = os.path.join(user_folder, fname)
            with open(fpath, 'wb') as f:
                f.write(content)
            if ext == '.py':
                handle_py_file(fpath, user_id, user_folder, fname, message)
            else:
                handle_js_file(fpath, user_id, user_folder, fname, message)
    except Exception as e:
        bot.reply_to(message, f"Upload error: {e}")

# ---------- Callback handlers (abbreviated but complete) ----------
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    if bot_locked and get_admin_setting('bot_lock_enabled') and user_id not in admin_ids and data not in ['back_to_main','speed','stats','mpx_ai','uptime']:
        bot.answer_callback_query(call.id, "Bot locked", show_alert=True)
        return
    # Permission settings menu
    if data == 'permissions_menu':
        if user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Admin only", show_alert=True)
            return
        bot.edit_message_text("⚙️ Admin Permission Settings\nToggle features:", call.message.chat.id, call.message.message_id, reply_markup=create_permissions_menu())
        bot.answer_callback_query(call.id)
        return
    if data.startswith('perm_'):
        handle_permissions_callback(call)
        return
    # Existing callbacks
    if data == 'upload':
        _logic_upload_file(call.message)
        bot.answer_callback_query(call.id)
    elif data == 'check_files':
        _logic_check_files(call.message)
        bot.answer_callback_query(call.id)
    elif data.startswith('file_'):
        _, owner, fname = data.split('_', 2)
        owner_id = int(owner)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Not your file", show_alert=True)
            return
        is_running = is_bot_running(owner_id, fname)
        markup = create_control_buttons(owner_id, fname, is_running)
        bot.edit_message_text(f"Controls for `{fname}`", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
        bot.answer_callback_query(call.id)
    elif data.startswith('start_'):
        _, owner, fname = data.split('_', 2)
        owner_id = int(owner)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "No permission", show_alert=True)
            return
        status = get_file_status(owner_id, fname)['status']
        if status != FILE_STATUS_APPROVED:
            bot.answer_callback_query(call.id, f"File not approved! Status: {status}", show_alert=True)
            return
        if is_bot_running(owner_id, fname):
            bot.answer_callback_query(call.id, "Already running", show_alert=True)
            return
        folder = get_user_folder(owner_id)
        fpath = os.path.join(folder, fname)
        ftype = next((ft for fn,ft in user_files.get(owner_id,[]) if fn==fname), 'py')
        if ftype == 'py':
            threading.Thread(target=run_script, args=(fpath, owner_id, folder, fname, call.message)).start()
        else:
            threading.Thread(target=run_js_script, args=(fpath, owner_id, folder, fname, call.message)).start()
        bot.answer_callback_query(call.id, f"Starting {fname}")
        time.sleep(1)
        is_now = is_bot_running(owner_id, fname)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_control_buttons(owner_id, fname, is_now))
    elif data.startswith('stop_'):
        _, owner, fname = data.split('_', 2)
        owner_id = int(owner)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "No permission", show_alert=True)
            return
        key = f"{owner_id}_{fname}"
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key])
            del bot_scripts[key]
        bot.answer_callback_query(call.id, f"Stopped {fname}")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_control_buttons(owner_id, fname, False))
    elif data.startswith('restart_'):
        _, owner, fname = data.split('_', 2)
        owner_id = int(owner)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "No permission", show_alert=True)
            return
        key = f"{owner_id}_{fname}"
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key])
            del bot_scripts[key]
            time.sleep(1)
        status = get_file_status(owner_id, fname)['status']
        if status != FILE_STATUS_APPROVED:
            bot.answer_callback_query(call.id, "Not approved", show_alert=True)
            return
        folder = get_user_folder(owner_id)
        fpath = os.path.join(folder, fname)
        ftype = next((ft for fn,ft in user_files.get(owner_id,[]) if fn==fname), 'py')
        if ftype == 'py':
            threading.Thread(target=run_script, args=(fpath, owner_id, folder, fname, call.message)).start()
        else:
            threading.Thread(target=run_js_script, args=(fpath, owner_id, folder, fname, call.message)).start()
        bot.answer_callback_query(call.id, f"Restarting {fname}")
        time.sleep(1)
        is_now = is_bot_running(owner_id, fname)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_control_buttons(owner_id, fname, is_now))
    elif data.startswith('delete_'):
        _, owner, fname = data.split('_', 2)
        owner_id = int(owner)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "No permission", show_alert=True)
            return
        key = f"{owner_id}_{fname}"
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key])
            del bot_scripts[key]
        folder = get_user_folder(owner_id)
        fpath = os.path.join(folder, fname)
        logpath = os.path.join(folder, f"{os.path.splitext(fname)[0]}.log")
        if os.path.exists(fpath): os.remove(fpath)
        if os.path.exists(logpath): os.remove(logpath)
        remove_user_file_db(owner_id, fname)
        # remove from approvals
        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute('DELETE FROM file_approvals WHERE user_id=? AND file_name=?', (owner_id, fname))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, f"Deleted {fname}")
        bot.edit_message_text(f"File `{fname}` deleted.", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    elif data.startswith('logs_'):
        _, owner, fname = data.split('_', 2)
        owner_id = int(owner)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "No permission", show_alert=True)
            return
        logpath = os.path.join(get_user_folder(owner_id), f"{os.path.splitext(fname)[0]}.log")
        if os.path.exists(logpath):
            with open(logpath, 'r', errors='ignore') as f:
                content = f.read()[-3000:]
            bot.send_message(call.message.chat.id, f"Logs for `{fname}`:\n```\n{content}\n```", parse_mode='Markdown')
        else:
            bot.send_message(call.message.chat.id, "No log file.")
        bot.answer_callback_query(call.id)
    elif data == 'speed':
        _logic_bot_speed(call.message)
        bot.answer_callback_query(call.id)
    elif data == 'stats':
        _logic_statistics(call.message)
        bot.answer_callback_query(call.id)
    elif data == 'uptime':
        _logic_uptime(call.message)
        bot.answer_callback_query(call.id)
    elif data == 'back_to_main':
        bot.edit_message_text("Main Menu", call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(user_id))
        bot.answer_callback_query(call.id)
    elif data == 'subscription':
        if user_id in admin_ids and get_admin_setting('subscription_manage'):
            bot.edit_message_text("Subscription Menu", call.message.chat.id, call.message.message_id, reply_markup=create_subscription_menu())
        else:
            bot.answer_callback_query(call.id, "No permission or disabled", show_alert=True)
    elif data == 'broadcast':
        if user_id in admin_ids and get_admin_setting('broadcast_enabled'):
            _logic_broadcast_init(call.message)
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "Broadcast disabled", show_alert=True)
    elif data == 'lock_bot':
        if user_id in admin_ids and get_admin_setting('bot_lock_enabled'):
            global bot_locked
            bot_locked = True
            bot.answer_callback_query(call.id, "Bot locked")
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(user_id))
        else:
            bot.answer_callback_query(call.id, "Not allowed", show_alert=True)
    elif data == 'unlock_bot':
        if user_id in admin_ids and get_admin_setting('bot_lock_enabled'):
            global bot_locked
            bot_locked = False
            bot.answer_callback_query(call.id, "Bot unlocked")
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(user_id))
        else:
            bot.answer_callback_query(call.id, "Not allowed", show_alert=True)
    elif data == 'run_all_scripts':
        if user_id in admin_ids and get_admin_setting('run_all_scripts'):
            _logic_run_all_scripts(call.message)
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "Disabled", show_alert=True)
    elif data == 'admin_panel':
        if user_id in admin_ids:
            bot.edit_message_text("Admin Panel", call.message.chat.id, call.message.message_id, reply_markup=create_admin_panel())
        else:
            bot.answer_callback_query(call.id, "Admin only", show_alert=True)
    elif data == 'add_admin':
        if user_id == OWNER_ID and get_admin_setting('admin_add_remove'):
            msg = bot.send_message(call.message.chat.id, "Send user ID to add as admin:")
            bot.register_next_step_handler(msg, process_add_admin_id)
        else:
            bot.answer_callback_query(call.id, "Not allowed (owner only)", show_alert=True)
    elif data == 'remove_admin':
        if user_id == OWNER_ID and get_admin_setting('admin_add_remove'):
            msg = bot.send_message(call.message.chat.id, "Send admin ID to remove:")
            bot.register_next_step_handler(msg, process_remove_admin_id)
        else:
            bot.answer_callback_query(call.id, "Not allowed", show_alert=True)
    elif data == 'list_admins':
        if user_id in admin_ids:
            admin_list = "\n".join(f"- `{aid}`" for aid in sorted(admin_ids))
            bot.send_message(call.message.chat.id, f"Admins:\n{admin_list}", parse_mode='Markdown')
        bot.answer_callback_query(call.id)
    elif data == 'view_pending':
        _logic_view_pending(call.message)
        bot.answer_callback_query(call.id)
    elif data == 'add_subscription':
        if user_id in admin_ids and get_admin_setting('subscription_manage'):
            msg = bot.send_message(call.message.chat.id, "Send: user_id days (e.g., 12345678 30)")
            bot.register_next_step_handler(msg, process_add_subscription_details)
        else:
            bot.answer_callback_query(call.id, "Disabled", show_alert=True)
    elif data == 'remove_subscription':
        if user_id in admin_ids and get_admin_setting('subscription_manage'):
            msg = bot.send_message(call.message.chat.id, "Send user ID to remove subscription:")
            bot.register_next_step_handler(msg, process_remove_subscription_id)
        else:
            bot.answer_callback_query(call.id, "Disabled", show_alert=True)
    elif data == 'check_subscription':
        if user_id in admin_ids and get_admin_setting('subscription_manage'):
            msg = bot.send_message(call.message.chat.id, "Send user ID to check:")
            bot.register_next_step_handler(msg, process_check_subscription_id)
        else:
            bot.answer_callback_query(call.id, "Disabled", show_alert=True)
    elif data.startswith('review_'):
        if user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Admin only", show_alert=True)
            return
        _, uid, fname = data.split('_', 2)
        uid = int(uid)
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f'approve_{uid}_{fname}'),
                   types.InlineKeyboardButton("❌ Reject", callback_data=f'reject_{uid}_{fname}'))
        markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='view_pending'))
        bot.edit_message_text(f"Review file: {fname} (user {uid})", call.message.chat.id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    elif data.startswith('approve_'):
        if user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Admin only", show_alert=True)
            return
        _, uid, fname = data.split('_', 2)
        uid = int(uid)
        if update_file_status(uid, fname, FILE_STATUS_APPROVED, user_id):
            bot.send_message(uid, f"✅ Your file `{fname}` has been APPROVED. You can now start it.", parse_mode='Markdown')
            bot.answer_callback_query(call.id, "Approved")
            bot.edit_message_text(f"✅ Approved {fname}", call.message.chat.id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "Error", show_alert=True)
    elif data.startswith('reject_'):
        if user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Admin only", show_alert=True)
            return
        _, uid, fname = data.split('_', 2)
        uid = int(uid)
        if update_file_status(uid, fname, FILE_STATUS_REJECTED, user_id):
            bot.send_message(uid, f"❌ Your file `{fname}` has been REJECTED. Contact admin.", parse_mode='Markdown')
            bot.answer_callback_query(call.id, "Rejected")
            bot.edit_message_text(f"❌ Rejected {fname}", call.message.chat.id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "Error", show_alert=True)
    elif data == 'mpx_ai':
        bot.send_message(call.message.chat.id, "Use /mpx your question")
        bot.answer_callback_query(call.id)
    elif data.startswith('confirm_broadcast_'):
        handle_confirm_broadcast(call)
    elif data == 'cancel_broadcast':
        handle_cancel_broadcast(call)
    else:
        bot.answer_callback_query(call.id, "Unknown action")

# Subscription step handlers
def process_add_subscription_details(message):
    if message.from_user.id not in admin_ids or not get_admin_setting('subscription_manage'):
        return
    try:
        uid, days = map(int, message.text.split())
        current = user_subscriptions.get(uid, {}).get('expiry', datetime.now())
        new_expiry = max(current, datetime.now()) + timedelta(days=days)
        save_subscription(uid, new_expiry)
        bot.reply_to(message, f"Subscription added for {uid}, expires {new_expiry.date()}")
    except:
        bot.reply_to(message, "Invalid format. Use: user_id days")

def process_remove_subscription_id(message):
    if message.from_user.id not in admin_ids or not get_admin_setting('subscription_manage'):
        return
    try:
        uid = int(message.text.strip())
        remove_subscription_db(uid)
        bot.reply_to(message, f"Subscription removed for {uid}")
    except:
        bot.reply_to(message, "Invalid ID")

def process_check_subscription_id(message):
    if message.from_user.id not in admin_ids or not get_admin_setting('subscription_manage'):
        return
    try:
        uid = int(message.text.strip())
        if uid in user_subscriptions:
            exp = user_subscriptions[uid]['expiry']
            bot.reply_to(message, f"User {uid} expires {exp.date()}" if exp > datetime.now() else f"User {uid} expired on {exp.date()}")
        else:
            bot.reply_to(message, f"No subscription for {uid}")
    except:
        bot.reply_to(message, "Invalid ID")

def process_add_admin_id(message):
    if message.from_user.id != OWNER_ID or not get_admin_setting('admin_add_remove'):
        return
    try:
        uid = int(message.text.strip())
        add_admin_db(uid)
        bot.reply_to(message, f"Admin added: {uid}")
    except:
        bot.reply_to(message, "Invalid ID")

def process_remove_admin_id(message):
    if message.from_user.id != OWNER_ID or not get_admin_setting('admin_add_remove'):
        return
    try:
        uid = int(message.text.strip())
        if remove_admin_db(uid):
            bot.reply_to(message, f"Admin removed: {uid}")
        else:
            bot.reply_to(message, "Failed (maybe owner)")
    except:
        bot.reply_to(message, "Invalid ID")

# ---------- Flask keep-alive ----------
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    logging.info("Keep-alive server started")

if __name__ == '__main__':
    keep_alive()
    logger.info("Bot starting on Render...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)