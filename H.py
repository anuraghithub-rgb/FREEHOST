# H.py - ULTIMATE PREMIUM VERSION WITH DELETE MANAGER
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
import hashlib

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
    return "🤖 Bot is running on Render with Malware Detection!"

@app.route('/health')
def health():
    return json.dumps({'status': 'ok', 'uptime': get_uptime()})

# ==================== CONFIGURATION ====================
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
OWNER_ID = int(os.environ.get('OWNER_ID', 8477195695))
ADMIN_ID = int(os.environ.get('ADMIN_ID', 8477195695))
YOUR_USERNAME = os.environ.get('YOUR_USERNAME', '@your_username')
UPDATE_CHANNEL = os.environ.get('UPDATE_CHANNEL', 'https://t.me/your_channel')

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

FILE_STATUS_PENDING = "pending"
FILE_STATUS_APPROVED = "approved"
FILE_STATUS_REJECTED = "rejected"

# ==================== PREMIUM BUTTONS LAYOUT ====================

# 🎨 Premium User Main Menu - Beautiful Glassmorphic Style
USER_MAIN_BUTTONS = [
    ["📢 ᴜᴘᴅᴀᴛᴇs", "⏱️ ᴜᴘᴛɪᴍᴇ", "📊 ꜱᴛᴀᴛꜱ"],
    ["📤 ᴜᴘʟᴏᴀᴅ ꜰɪʟᴇ", "📂 ᴍʏ ꜰɪʟᴇꜱ", "⚡ ʙᴏᴛ ꜱᴘᴇᴇᴅ"],
    ["🤖 ᴍᴘx ᴀɪ", "👤 ᴘʀᴏꜰɪʟᴇ", "📞 ᴄᴏɴᴛᴀᴄᴛ"],
    ["🗑️ ᴅᴇʟᴇᴛᴇ ᴍᴀɴᴀɢᴇʀ", "🔍 ᴄʜᴇᴄᴋ ꜱᴛᴀᴛᴜꜱ", "🔄 ʀᴇꜰʀᴇꜱʜ"]
]

# 👑 Premium Admin Main Menu
ADMIN_MAIN_BUTTONS = [
    ["📢 ᴜᴘᴅᴀᴛᴇꜱ", "⏱️ ᴜᴘᴛɪᴍᴇ", "📊 ꜱᴛᴀᴛꜱ"],
    ["📤 ᴜᴘʟᴏᴀᴅ ꜰɪʟᴇ", "📂 ᴍʏ ꜰɪʟᴇꜱ", "⚡ ʙᴏᴛ ꜱᴘᴇᴇᴅ"],
    ["🤖 ᴍᴘx ᴀɪ", "👤 ᴘʀᴏꜰɪʟᴇ", "📞 ᴄᴏɴᴛᴀᴄᴛ"],
    ["💳 ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴꜱ", "📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ", "🔒 ʟᴏᴄᴋ ʙᴏᴛ"],
    ["👑 ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ", "🟢 ʀᴜɴ ᴀʟʟ", "📋 ᴘᴇɴᴅɪɴɢ", "🗑️ ᴅᴇʟᴇᴛᴇ ᴍɢʀ"]
]

# 🎨 Premium File Control Buttons
def get_premium_file_buttons(script_owner_id, file_name, is_running):
    """Beautiful file control buttons"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🛑 ꜱᴛᴏᴘ", callback_data=f'stop_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 ʀᴇꜱᴛᴀʀᴛ", callback_data=f'restart_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ ᴅᴇʟᴇᴛᴇ", callback_data=f'delete_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 ᴠɪᴇᴡ ʟᴏɢꜱ", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("▶️ ꜱᴛᴀʀᴛ", callback_data=f'start_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🗑️ ᴅᴇʟᴇᴛᴇ", callback_data=f'delete_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("📜 ᴠɪᴇᴡ ʟᴏɢꜱ", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    
    file_status = get_file_status(script_owner_id, file_name)
    status_text = "✅ ᴀᴘᴘʀᴏᴠᴇᴅ" if file_status['status'] == FILE_STATUS_APPROVED else "⏳ ᴘᴇɴᴅɪɴɢ" if file_status['status'] == FILE_STATUS_PENDING else "❌ ʀᴇᴊᴇᴄᴛᴇᴅ"
    
    markup.add(types.InlineKeyboardButton(f"📋 {status_text}", callback_data=f'status_{script_owner_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("🔙 ʙᴀᴄᴋ ᴛᴏ ꜰɪʟᴇꜱ", callback_data='check_files'))
    
    return markup

# 🎨 Premium Delete Manager Buttons
def get_delete_manager_buttons(user_id):
    """Beautiful delete manager buttons for selecting files to delete"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        return None
    
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        status_icon = "🟢" if is_running else "⚪"
        markup.add(types.InlineKeyboardButton(
            f"{status_icon} {file_name} [{file_type.upper()}]", 
            callback_data=f'select_delete_{user_id}_{file_name}'
        ))
    
    markup.add(types.InlineKeyboardButton("🔙 ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ", callback_data='back_to_main'))
    return markup

def get_confirm_delete_buttons(user_id, file_name):
    """Beautiful confirmation buttons for delete"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("✅ ᴄᴏɴꜰɪʀᴍ ᴅᴇʟᴇᴛᴇ", callback_data=f'confirm_delete_{user_id}_{file_name}'),
        types.InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data=f'cancel_delete_{user_id}_{file_name}')
    )
    return markup

# ==================== MALWARE DETECTION SYSTEM ====================
SUSPICIOUS_PATTERNS = [
    r'eval\s*\(', r'exec\s*\(', r'__import__\s*\(', r'os\.system\s*\(',
    r'subprocess\.call\s*\(', r'subprocess\.Popen\s*\(', r'os\.popen\s*\(',
    r'os\.remove\s*\(', r'shutil\.rmtree\s*\(', r'socket\.socket',
    r'base64\.b64decode', r'sudo', r'chmod', r'crypto', r'miner', r'encrypt'
]

SAFE_PATTERNS = [r'print\s*\(', r'bot\.send_message', r'telebot', r'flask']

def scan_file_for_malware(file_path, file_type):
    try:
        if file_type == 'py':
            return scan_python_file(file_path)
        elif file_type == 'js':
            return scan_javascript_file(file_path)
        elif file_type == 'zip':
            return scan_zip_file(file_path)
        return (False, "Unknown file type")
    except Exception as e:
        logger.error(f"Malware scan error: {e}")
        return (True, f"Scan error: {str(e)}")

def scan_python_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        for pattern in SUSPICIOUS_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                is_safe = False
                for safe_pattern in SAFE_PATTERNS:
                    if re.search(safe_pattern, content, re.IGNORECASE):
                        is_safe = True
                        break
                if not is_safe:
                    return (True, f"Suspicious pattern found: {pattern}")
        
        if len(content) > 0:
            ascii_ratio = sum(1 for c in content if 32 <= ord(c) <= 126) / len(content)
            if ascii_ratio < 0.5:
                return (True, "Low ASCII ratio (possible encoded malware)")
        
        return (False, "Clean")
    except Exception as e:
        return (True, f"Scan error: {str(e)}")

def scan_javascript_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        js_suspicious = [r'eval\s*\(', r'child_process\.exec', r'require\s*\(\s*[\'"]child_process', r'vm\.runInNewContext']
        
        for pattern in js_suspicious:
            if re.search(pattern, content, re.IGNORECASE):
                return (True, f"Suspicious JS pattern: {pattern}")
        return (False, "Clean")
    except Exception as e:
        return (True, f"Scan error: {str(e)}")

def scan_zip_file(file_path):
    try:
        suspicious_files = []
        temp_dir = tempfile.mkdtemp(prefix="malware_scan_")
        
        with zipfile.ZipFile(file_path, 'r') as zf:
            for member in zf.infolist():
                if member.filename.endswith('.py') or member.filename.endswith('.js'):
                    try:
                        extracted_path = zf.extract(member, temp_dir)
                        file_type = 'py' if member.filename.endswith('.py') else 'js'
                        is_malicious, reason = scan_file_for_malware(extracted_path, file_type)
                        if is_malicious:
                            suspicious_files.append(f"{member.filename}: {reason}")
                    except Exception as e:
                        suspicious_files.append(f"{member.filename}: Extract error - {e}")
        
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        if suspicious_files:
            return (True, f"Suspicious files in ZIP: {', '.join(suspicious_files[:3])}")
        return (False, "Clean")
    except Exception as e:
        return (True, f"ZIP scan error: {str(e)}")

# ==================== DATABASE FUNCTIONS ====================
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
                logger.warning(f"Invalid expiry date format for user {user_id}")

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
        logger.info(f"Data loaded: {len(active_users)} users")
    except Exception as e:
        logger.error(f"Error loading data: {e}", exc_info=True)

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
            return 0
        finally:
            conn.close()

def send_file_for_approval(message, user_id, file_name, file_type):
    user = message.from_user
    file_info = (
        f"╔════════════════════════════════╗\n"
        f"║     ⚠️ NEW FILE FOR APPROVAL     ║\n"
        f"╠════════════════════════════════╣\n"
        f"║ 👤 User: {user.first_name}\n"
        f"║ 📛 @{user.username or 'N/A'}\n"
        f"║ 🆔 ID: `{user_id}`\n"
        f"║ 📁 File: `{file_name}`\n"
        f"║ 📊 Type: {file_type}\n"
        f"║ ⚠️ MALWARE DETECTED\n"
        f"║ 🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"╚════════════════════════════════╝"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ ᴀᴘᴘʀᴏᴠᴇ", callback_data=f'approve_{user_id}_{file_name}'),
        types.InlineKeyboardButton("❌ ʀᴇᴊᴇᴄᴛ", callback_data=f'reject_{user_id}_{file_name}')
    )
    markup.add(types.InlineKeyboardButton("📋 ᴠɪᴇᴡ ᴀʟʟ ᴘᴇɴᴅɪɴɢ", callback_data='view_pending'))
    
    for admin_id in admin_ids:
        try:
            bot.forward_message(admin_id, message.chat.id, message.message_id)
            bot.send_message(admin_id, file_info, reply_markup=markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send file for approval to admin {admin_id}: {e}")

# ==================== USER FILE MANAGEMENT ====================
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

def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)',
                      (user_id, file_name, file_type))
            conn.commit()
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
        except Exception as e:
            logger.error(f"Error saving file: {e}")
        finally:
            conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
                if not user_files[user_id]:
                    del user_files[user_id]
        except Exception as e:
            logger.error(f"Error removing file: {e}")
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
        except Exception as e:
            logger.error(f"Error adding active user: {e}")
        finally:
            conn.close()

def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            expiry_str = expiry.isoformat()
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)', (user_id, expiry_str))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry}
        except Exception as e:
            logger.error(f"Error saving subscription: {e}")
        finally:
            conn.close()

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_subscriptions:
                del user_subscriptions[user_id]
        except Exception as e:
            logger.error(f"Error removing subscription: {e}")
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
        except Exception as e:
            logger.error(f"Error adding admin: {e}")
        finally:
            conn.close()

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID:
        return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
            conn.commit()
            removed = c.rowcount > 0
            if removed:
                admin_ids.discard(admin_id)
            return removed
        except Exception as e:
            logger.error(f"Error removing admin: {e}")
            return False
        finally:
            conn.close()

# ==================== BOT RUNNING FUNCTIONS ====================
def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not is_running:
                if 'log_file' in script_info and script_info['log_file'] and not script_info['log_file'].closed:
                    try:
                        script_info['log_file'].close()
                    except:
                        pass
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            if 'log_file' in script_info and script_info['log_file'] and not script_info['log_file'].closed:
                try:
                    script_info['log_file'].close()
                except:
                    pass
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            return False
        except Exception as e:
            logger.error(f"Error checking process status: {e}")
            return False
    return False

def kill_process_tree(process_info):
    try:
        if 'log_file' in process_info and process_info['log_file'] and not process_info['log_file'].closed:
            try:
                process_info['log_file'].close()
            except:
                pass
        
        process = process_info.get('process')
        if process and hasattr(process, 'pid') and process.pid:
            try:
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except:
                        try:
                            child.kill()
                        except:
                            pass
                try:
                    parent.terminate()
                    parent.wait(timeout=1)
                except:
                    try:
                        parent.kill()
                    except:
                        pass
            except psutil.NoSuchProcess:
                pass
    except Exception as e:
        logger.error(f"Error killing process: {e}")

TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI', 'requests': 'requests', 'flask': 'Flask',
    'psutil': 'psutil', 'sqlite3': None, 'json': None, 'datetime': None,
    'os': None, 'sys': None, 're': None, 'time': None, 'threading': None
}

def attempt_install_pip(module_name, message):
    package_name = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    if package_name is None:
        return False
    try:
        bot.reply_to(message, f"📦 Installing `{package_name}`...", parse_mode='Markdown')
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', package_name], 
                               capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            bot.reply_to(message, f"✅ Package `{package_name}` installed.", parse_mode='Markdown')
            return True
        else:
            bot.reply_to(message, f"❌ Failed to install `{package_name}`", parse_mode='Markdown')
            return False
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")
        return False

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    file_status = get_file_status(script_owner_id, file_name)
    if file_status['status'] != FILE_STATUS_APPROVED:
        bot.reply_to(message_obj_for_reply,
                    f"❌ File `{file_name}` not approved!\nStatus: {file_status['status'].upper()}",
                    parse_mode='Markdown')
        return
    
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run '{file_name}' after {max_attempts} attempts.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"❌ Script '{file_name}' not found!")
            return

        if attempt == 1:
            check_proc = None
            try:
                check_proc = subprocess.Popen([sys.executable, script_path], cwd=user_folder, 
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                if stderr:
                    match_py = re.search(r"ModuleNotFoundError: No module named '(.+?)'", stderr)
                    if match_py:
                        module_name = match_py.group(1)
                        if attempt_install_pip(module_name, message_obj_for_reply):
                            time.sleep(2)
                            threading.Thread(target=run_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                            return
            except subprocess.TimeoutExpired:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()
            except Exception as e:
                logger.error(f"Error in pre-check: {e}")
            finally:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()

        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        
        process = subprocess.Popen(
            [sys.executable, script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
            stdin=subprocess.PIPE, encoding='utf-8', errors='ignore'
        )
        
        bot_scripts[script_key] = {
            'process': process, 'log_file': log_file, 'file_name': file_name,
            'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id,
            'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'py'
        }
        bot.reply_to(message_obj_for_reply, f"✅ Python script '{file_name}' started! (PID: {process.pid})")
        
    except Exception as e:
        logger.error(f"Error running script: {e}")
        bot.reply_to(message_obj_for_reply, f"❌ Error: {str(e)}")

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    file_status = get_file_status(script_owner_id, file_name)
    if file_status['status'] != FILE_STATUS_APPROVED:
        bot.reply_to(message_obj_for_reply,
                    f"❌ File `{file_name}` not approved!\nStatus: {file_status['status'].upper()}",
                    parse_mode='Markdown')
        return
    
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run '{file_name}'")
        return

    script_key = f"{script_owner_id}_{file_name}"
    
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"❌ Script '{file_name}' not found!")
            return

        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        
        process = subprocess.Popen(
            ['node', script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
            stdin=subprocess.PIPE, encoding='utf-8', errors='ignore'
        )
        
        bot_scripts[script_key] = {
            'process': process, 'log_file': log_file, 'file_name': file_name,
            'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id,
            'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'js'
        }
        bot.reply_to(message_obj_for_reply, f"✅ JS script '{file_name}' started! (PID: {process.pid})")
        
    except FileNotFoundError:
        bot.reply_to(message_obj_for_reply, "❌ 'node' not found. Install Node.js")
    except Exception as e:
        logger.error(f"Error running JS script: {e}")
        bot.reply_to(message_obj_for_reply, f"❌ Error: {str(e)}")

# ==================== FILE HANDLING ====================
def handle_zip_file(downloaded_file_content, file_name_zip, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as new_file:
            new_file.write(downloaded_file_content)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.infolist():
                member_path = os.path.abspath(os.path.join(temp_dir, member.filename))
                if not member_path.startswith(os.path.abspath(temp_dir)):
                    raise zipfile.BadZipFile(f"Unsafe path: {member.filename}")
            zip_ref.extractall(temp_dir)

        extracted_items = os.listdir(temp_dir)
        py_files = [f for f in extracted_items if f.endswith('.py')]
        js_files = [f for f in extracted_items if f.endswith('.js')]
        
        main_script_name = None
        file_type = None
        
        for p in ['main.py', 'bot.py', 'app.py']:
            if p in py_files:
                main_script_name = p
                file_type = 'py'
                break
        
        if not main_script_name:
            for p in ['index.js', 'main.js', 'bot.js']:
                if p in js_files:
                    main_script_name = p
                    file_type = 'js'
                    break
        
        if not main_script_name and py_files:
            main_script_name = py_files[0]
            file_type = 'py'
        elif not main_script_name and js_files:
            main_script_name = js_files[0]
            file_type = 'js'
        
        if not main_script_name:
            bot.reply_to(message, "❌ No `.py` or `.js` script found!")
            return

        for item_name in os.listdir(temp_dir):
            src_path = os.path.join(temp_dir, item_name)
            dest_path = os.path.join(user_folder, item_name)
            if os.path.isdir(dest_path):
                shutil.rmtree(dest_path)
            elif os.path.exists(dest_path):
                os.remove(dest_path)
            shutil.move(src_path, dest_path)

        temp_script_path = os.path.join(user_folder, main_script_name)
        is_malicious, reason = scan_file_for_malware(temp_script_path, file_type)
        
        save_user_file(user_id, main_script_name, file_type)
        
        if is_malicious:
            logger.warning(f"Malware detected in ZIP: {reason}")
            save_file_approval(user_id, main_script_name, file_type, FILE_STATUS_PENDING)
            send_file_for_approval(message, user_id, main_script_name, file_type)
            bot.reply_to(message, 
                        f"⚠️ **MALWARE DETECTED!**\n\n📁 `{main_script_name}`\n🔍 {reason}\n📋 Status: PENDING ADMIN REVIEW", 
                        parse_mode='Markdown')
        else:
            save_file_approval(user_id, main_script_name, file_type, FILE_STATUS_APPROVED, user_id)
            bot.reply_to(message, 
                        f"✅ **ZIP EXTRACTED & APPROVED!**\n\n📁 Main: `{main_script_name}`\n✅ Status: AUTO-APPROVED", 
                        parse_mode='Markdown')

    except zipfile.BadZipFile as e:
        bot.reply_to(message, f"❌ Invalid ZIP file: {e}")
    except Exception as e:
        logger.error(f"Error processing zip: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

def handle_py_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        is_malicious, reason = scan_file_for_malware(file_path, 'py')
        
        if is_malicious:
            logger.warning(f"Malware detected in {file_name}: {reason}")
            save_user_file(script_owner_id, file_name, 'py')
            save_file_approval(script_owner_id, file_name, 'py', FILE_STATUS_PENDING)
            send_file_for_approval(message, script_owner_id, file_name, 'py')
            bot.reply_to(message,
                        f"⚠️ **MALWARE DETECTED!**\n\n📁 `{file_name}`\n🔍 {reason}\n📋 Status: PENDING ADMIN REVIEW",
                        parse_mode='Markdown')
        else:
            save_user_file(script_owner_id, file_name, 'py')
            save_file_approval(script_owner_id, file_name, 'py', FILE_STATUS_APPROVED, script_owner_id)
            bot.reply_to(message,
                        f"✅ **FILE APPROVED!**\n\n📁 `{file_name}`\n✅ Status: CLEAN - AUTO-APPROVED",
                        parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error processing Python file: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

def handle_js_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        is_malicious, reason = scan_file_for_malware(file_path, 'js')
        
        if is_malicious:
            logger.warning(f"Malware detected in JS {file_name}: {reason}")
            save_user_file(script_owner_id, file_name, 'js')
            save_file_approval(script_owner_id, file_name, 'js', FILE_STATUS_PENDING)
            send_file_for_approval(message, script_owner_id, file_name, 'js')
            bot.reply_to(message,
                        f"⚠️ **MALWARE DETECTED!**\n\n📁 `{file_name}`\n🔍 {reason}\n📋 Status: PENDING ADMIN REVIEW",
                        parse_mode='Markdown')
        else:
            save_user_file(script_owner_id, file_name, 'js')
            save_file_approval(script_owner_id, file_name, 'js', FILE_STATUS_APPROVED, script_owner_id)
            bot.reply_to(message,
                        f"✅ **JS FILE APPROVED!**\n\n📁 `{file_name}`\n✅ Status: CLEAN - AUTO-APPROVED",
                        parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error processing JS file: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ==================== UI FUNCTIONS ====================
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    buttons = [
        types.InlineKeyboardButton('📢 ᴜᴘᴅᴀᴛᴇꜱ', url=UPDATE_CHANNEL),
        types.InlineKeyboardButton('📤 ᴜᴘʟᴏᴀᴅ', callback_data='upload'),
        types.InlineKeyboardButton('📂 ᴍʏ ꜰɪʟᴇꜱ', callback_data='check_files'),
        types.InlineKeyboardButton('⚡ ꜱᴘᴇᴇᴅ', callback_data='speed'),
        types.InlineKeyboardButton('📊 ꜱᴛᴀᴛꜱ', callback_data='stats'),
        types.InlineKeyboardButton('📞 ᴄᴏɴᴛᴀᴄᴛ', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'),
        types.InlineKeyboardButton('🤖 ᴍᴘx ᴀɪ', callback_data='mpx_ai'),
        types.InlineKeyboardButton('🗑️ ᴅᴇʟᴇᴛᴇ ᴍɢʀ', callback_data='delete_manager'),
        types.InlineKeyboardButton('👤 ᴘʀᴏꜰɪʟᴇ', callback_data='profile'),
        types.InlineKeyboardButton('⏱️ ᴜᴘᴛɪᴍᴇ', callback_data='uptime')
    ]
    
    for btn in buttons:
        markup.add(btn)
    
    if user_id in admin_ids:
        pending_count = get_pending_files_count()
        pending_text = f"📋 ᴘᴇɴᴅɪɴɢ ({pending_count})" if pending_count > 0 else "📋 ᴘᴇɴᴅɪɴɢ"
        
        admin_buttons = [
            types.InlineKeyboardButton(pending_text, callback_data='view_pending'),
            types.InlineKeyboardButton('💳 ꜱᴜʙꜱ', callback_data='subscription'),
            types.InlineKeyboardButton('📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ', callback_data='broadcast'),
            types.InlineKeyboardButton('🔒 ʟᴏᴄᴋ' if not bot_locked else '🔓 ᴜɴʟᴏᴄᴋ', callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
            types.InlineKeyboardButton('👑 ᴀᴅᴍɪɴ', callback_data='admin_panel'),
            types.InlineKeyboardButton('🟢 ʀᴜɴ ᴀʟʟ', callback_data='run_all_scripts')
        ]
        for btn in admin_buttons:
            markup.add(btn)
    
    return markup

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    layout_to_use = ADMIN_MAIN_BUTTONS if user_id in admin_ids else USER_MAIN_BUTTONS
    
    for row_buttons in layout_to_use:
        buttons = [types.KeyboardButton(text) for text in row_buttons]
        markup.row(*buttons)
    
    return markup

def create_control_buttons(script_owner_id, file_name, is_running=True):
    return get_premium_file_buttons(script_owner_id, file_name, is_running)

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ ᴀᴅᴅ ᴀᴅᴍɪɴ', callback_data='add_admin'),
        types.InlineKeyboardButton('➖ ʀᴇᴍᴏᴠᴇ ᴀᴅᴍɪɴ', callback_data='remove_admin')
    )
    markup.row(
        types.InlineKeyboardButton('📋 ʟɪꜱᴛ ᴀᴅᴍɪɴꜱ', callback_data='list_admins'),
        types.InlineKeyboardButton('📋 ᴘᴇɴᴅɪɴɢ ꜰɪʟᴇꜱ', callback_data='view_pending')
    )
    markup.row(types.InlineKeyboardButton('🔙 ʙᴀᴄᴋ', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ ᴀᴅᴅ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ', callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ ʀᴇᴍᴏᴠᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ', callback_data='remove_subscription')
    )
    markup.row(types.InlineKeyboardButton('🔍 ᴄʜᴇᴄᴋ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 ʙᴀᴄᴋ', callback_data='back_to_main'))
    return markup

# ==================== MESSAGE HANDLERS ====================
def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "🔒 Bot is locked. Try later.")
        return

    if user_id not in active_users:
        add_active_user(user_id)
        try:
            bot.send_message(OWNER_ID, f"🆕 New user!\nName: {user_name}\nID: `{user_id}`", parse_mode='Markdown')
        except:
            pass

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = "∞" if file_limit == float('inf') else str(file_limit)
    
    if user_id == OWNER_ID:
        user_status = "👑 OWNER"
    elif user_id in admin_ids:
        user_status = "👮 ADMIN"
    elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now():
        user_status = "⭐ PREMIUM"
    else:
        user_status = "🆓 FREE"

    welcome_msg = f"""
╔════════════════════════════════╗
║      🤖 WELCOME TO BOT         ║
╠════════════════════════════════╣
║ 👤 {user_name}
║ 🆔 `{user_id}`
║ 📊 Status: {user_status}
║ 📁 Files: {current_files}/{limit_str}
╠════════════════════════════════╣
║ 🛡️ AUTO MALWARE DETECTION
║ ✅ Clean files auto-approved
║ ⚠️ Suspicious → Admin review
╠════════════════════════════════╣
║ Use buttons below to start!
╚════════════════════════════════╝
"""
    main_reply_markup = create_reply_keyboard_main_menu(user_id)
    bot.send_message(chat_id, welcome_msg, reply_markup=main_reply_markup, parse_mode='Markdown')

def _logic_profile(message):
    user_id = message.from_user.id
    profile_text = get_user_profile(user_id)
    bot.reply_to(message, profile_text, parse_mode='Markdown')

def _logic_help(message):
    help_text = get_help_menu()
    bot.reply_to(message, help_text, parse_mode='Markdown')

def _logic_delete_manager(message):
    user_id = message.from_user.id
    markup = get_delete_manager_buttons(user_id)
    if markup is None:
        bot.reply_to(message, "📂 No files to delete!")
        return
    
    bot.reply_to(message, "🗑️ **DELETE MANAGER**\n\nSelect a file to delete:", 
                 reply_markup=markup, parse_mode='Markdown')

def _logic_updates_channel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📢 ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ', url=UPDATE_CHANNEL))
    bot.reply_to(message, "📢 **Our Updates Channel:**", reply_markup=markup, parse_mode='Markdown')

def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "🔒 Bot locked, cannot accept files.")
        return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "∞"
        bot.reply_to(message, f"❌ File limit reached! ({current_files}/{limit_str})")
        return
    
    bot.reply_to(message, 
                "📤 **Send your file:**\n\n"
                "✅ Supported: `.py`, `.js`, `.zip`\n"
                "🛡️ Auto malware scan active\n"
                "📁 Max size: 20MB", 
                parse_mode='Markdown')

def _logic_check_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    
    if not user_files_list:
        bot.reply_to(message, "📂 **Your Files:**\n\n(No files uploaded yet)", parse_mode='Markdown')
        return
    
    response = "📂 **YOUR FILES**\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        file_status = get_file_status(user_id, file_name)
        
        status_icon = "🟢" if is_running else "⚪"
        approval_icon = "✅" if file_status['status'] == FILE_STATUS_APPROVED else "⚠️" if file_status['status'] == FILE_STATUS_PENDING else "❌"
        
        btn_text = f"{approval_icon} {file_name} [{file_type.upper()}] {status_icon}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))
    
    markup.add(types.InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data='back_to_main'))
    bot.reply_to(message, response, reply_markup=markup, parse_mode='Markdown')

def _logic_bot_speed(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    start_time_ping = time.time()
    wait_msg = bot.reply_to(message, "⏳ Testing speed...")
    
    response_time = round((time.time() - start_time_ping) * 1000, 2)
    status = "🔓 UNLOCKED" if not bot_locked else "🔒 LOCKED"
    
    if user_id == OWNER_ID:
        user_level = "👑 OWNER"
    elif user_id in admin_ids:
        user_level = "👮 ADMIN"
    elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now():
        user_level = "⭐ PREMIUM"
    else:
        user_level = "🆓 FREE"
    
    speed_msg = f"""
╔════════════════════════════╗
║       ⚡ BOT SPEED          ║
╠════════════════════════════╣
║ 📡 Response: {response_time} ms
║ 🔓 Status: {status}
║ 👤 Level: {user_level}
╚════════════════════════════╝
"""
    bot.edit_message_text(speed_msg, chat_id, wait_msg.message_id, parse_mode='Markdown')

def _logic_statistics(message):
    total_users = len(active_users)
    total_files = sum(len(files) for files in user_files.values())
    running_bots = len(bot_scripts)
    
    stats_msg = f"""
╔════════════════════════════╗
║      📊 STATISTICS          ║
╠════════════════════════════╣
║ 👥 Users: {total_users}
║ 📁 Files: {total_files}
║ ▶️ Running: {running_bots}
╚════════════════════════════╝
"""
    bot.reply_to(message, stats_msg, parse_mode='Markdown')

def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📞 ᴄᴏɴᴛᴀᴄᴛ ᴏᴡɴᴇʀ', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    bot.reply_to(message, "📞 **Contact Owner:**", reply_markup=markup, parse_mode='Markdown')

def _logic_uptime(message):
    uptime_str = get_uptime()
    bot.reply_to(message, f"⏱️ **Bot Uptime:** `{uptime_str}`", parse_mode='Markdown')

def _logic_subscriptions_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "❌ Admin permissions required.")
        return
    bot.reply_to(message, "💳 **Subscription Management**", reply_markup=create_subscription_menu(), parse_mode='Markdown')

def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "❌ Admin permissions required.")
        return
    bot.reply_to(message, "👑 **Admin Panel**", reply_markup=create_admin_panel(), parse_mode='Markdown')

def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "❌ Admin permissions required.")
        return
    global bot_locked
    bot_locked = not bot_locked
    status = "🔒 LOCKED" if bot_locked else "🔓 UNLOCKED"
    bot.reply_to(message, f"🔐 Bot has been {status}.")

def _logic_run_all_scripts(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "❌ Admin permissions required.")
        return
    
    bot.reply_to(message, "🔄 Starting all approved scripts...")
    
    started_count = 0
    for target_user_id, files_for_user in dict(user_files).items():
        for file_name, file_type in files_for_user:
            file_status = get_file_status(target_user_id, file_name)
            if file_status['status'] != FILE_STATUS_APPROVED:
                continue
            if not is_bot_running(target_user_id, file_name):
                file_path = os.path.join(get_user_folder(target_user_id), file_name)
                if os.path.exists(file_path):
                    if file_type == 'py':
                        threading.Thread(target=run_script, args=(file_path, target_user_id, get_user_folder(target_user_id), file_name, message)).start()
                        started_count += 1
                    elif file_type == 'js':
                        threading.Thread(target=run_js_script, args=(file_path, target_user_id, get_user_folder(target_user_id), file_name, message)).start()
                        started_count += 1
                time.sleep(0.5)
    
    bot.send_message(message.chat.id, f"✅ Started {started_count} scripts!")

def _logic_broadcast_init(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "❌ Admin permissions required.")
        return
    msg = bot.reply_to(message, "📢 Send message to broadcast.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def process_broadcast_message(message):
    user_id = message.from_user.id
    if user_id not in admin_ids:
        return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Broadcast cancelled.")
        return

    broadcast_content = message.text
    if not broadcast_content:
        bot.reply_to(message, "❌ Cannot broadcast empty message.")
        return

    target_count = len(active_users)
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ ᴄᴏɴꜰɪʀᴍ", callback_data=f"confirm_broadcast_{message.message_id}"),
        types.InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="cancel_broadcast")
    )

    bot.reply_to(message, f"📢 **Confirm Broadcast**\n\nTo **{target_count}** users?\n\nPreview:\n```\n{broadcast_content[:200]}\n```", 
                 reply_markup=markup, parse_mode='Markdown')

def handle_confirm_broadcast(call):
    user_id = call.from_user.id
    if user_id not in admin_ids:
        bot.answer_callback_query(call.id, "❌ Admin only", show_alert=True)
        return
    
    original_message = call.message.reply_to_message
    if not original_message or not original_message.text:
        bot.answer_callback_query(call.id, "❌ Invalid broadcast message", show_alert=True)
        return
    
    broadcast_text = original_message.text
    bot.answer_callback_query(call.id, "📢 Broadcasting...")
    
    sent_count = 0
    for user_id_bc in list(active_users):
        try:
            bot.send_message(user_id_bc, broadcast_text, parse_mode='Markdown')
            sent_count += 1
        except:
            pass
        time.sleep(0.05)
    
    bot.edit_message_text(f"✅ Broadcast complete!\n\nSent to {sent_count} users", 
                          call.message.chat.id, call.message.message_id)

def handle_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "❌ Broadcast cancelled")
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ==================== CALLBACK HANDLERS ====================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    logger.info(f"Callback: {data} from {user_id}")

    if bot_locked and user_id not in admin_ids and data not in ['back_to_main', 'speed', 'stats', 'mpx_ai', 'uptime', 'profile']:
        bot.answer_callback_query(call.id, "🔒 Bot locked", show_alert=True)
        return

    # DELETE MANAGER CALLBACKS
    if data.startswith('select_delete_'):
        try:
            _, _, user_id_str, file_name = data.split('_', 3)
            target_user_id = int(user_id_str)
            if user_id != target_user_id and user_id not in admin_ids:
                bot.answer_callback_query(call.id, "❌ Permission denied", show_alert=True)
                return
            markup = get_confirm_delete_buttons(target_user_id, file_name)
            bot.answer_callback_query(call.id)
            bot.edit_message_text(f"🗑️ Delete `{file_name}`?\n\nThis action cannot be undone!",
                                 call.message.chat.id, call.message.message_id, 
                                 reply_markup=markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error in select_delete: {e}")
    
    elif data.startswith('confirm_delete_'):
        try:
            _, _, user_id_str, file_name = data.split('_', 3)
            target_user_id = int(user_id_str)
            if user_id != target_user_id and user_id not in admin_ids:
                bot.answer_callback_query(call.id, "❌ Permission denied", show_alert=True)
                return
            
            # Stop if running
            if is_bot_running(target_user_id, file_name):
                script_key = f"{target_user_id}_{file_name}"
                if script_key in bot_scripts:
                    kill_process_tree(bot_scripts[script_key])
                    del bot_scripts[script_key]
            
            # Delete files
            user_folder = get_user_folder(target_user_id)
            file_path = os.path.join(user_folder, file_name)
            log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
            
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(log_path):
                os.remove(log_path)
            
            # Remove from DB
            remove_user_file_db(target_user_id, file_name)
            
            # Remove from approvals
            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH)
                c = conn.cursor()
                c.execute('DELETE FROM file_approvals WHERE user_id=? AND file_name=?', (target_user_id, file_name))
                conn.commit()
                conn.close()
            
            bot.answer_callback_query(call.id, f"✅ Deleted: {file_name}")
            bot.edit_message_text(f"✅ **Deleted:** `{file_name}`", 
                                 call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error in confirm_delete: {e}")
            bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)
    
    elif data.startswith('cancel_delete_'):
        bot.answer_callback_query(call.id, "❌ Deletion cancelled")
        _logic_check_files(call.message)
    
    # PROFILE
    elif data == 'profile':
        bot.answer_callback_query(call.id)
        profile_text = get_user_profile(user_id)
        bot.send_message(call.message.chat.id, profile_text, parse_mode='Markdown')
    
    # DELETE MANAGER MENU
    elif data == 'delete_manager':
        bot.answer_callback_query(call.id)
        _logic_delete_manager(call.message)
    
    # OTHER CALLBACKS
    elif data == 'upload':
        upload_callback(call)
    elif data == 'check_files':
        check_files_callback(call)
    elif data.startswith('file_'):
        file_control_callback(call)
    elif data.startswith('start_'):
        start_bot_callback(call)
    elif data.startswith('stop_'):
        stop_bot_callback(call)
    elif data.startswith('restart_'):
        restart_bot_callback(call)
    elif data.startswith('delete_'):
        delete_bot_callback(call)
    elif data.startswith('logs_'):
        logs_bot_callback(call)
    elif data.startswith('status_'):
        status_callback(call)
    elif data == 'speed':
        speed_callback(call)
    elif data == 'back_to_main':
        back_to_main_callback(call)
    elif data == 'subscription':
        subscription_management_callback(call)
    elif data == 'stats':
        stats_callback(call)
    elif data == 'lock_bot':
        lock_bot_callback(call)
    elif data == 'unlock_bot':
        unlock_bot_callback(call)
    elif data == 'run_all_scripts':
        run_all_scripts_callback(call)
    elif data == 'broadcast':
        broadcast_init_callback(call)
    elif data == 'admin_panel':
        admin_panel_callback(call)
    elif data == 'add_admin':
        add_admin_init_callback(call)
    elif data == 'remove_admin':
        remove_admin_init_callback(call)
    elif data == 'list_admins':
        list_admins_callback(call)
    elif data == 'add_subscription':
        add_subscription_init_callback(call)
    elif data == 'remove_subscription':
        remove_subscription_init_callback(call)
    elif data == 'check_subscription':
        check_subscription_init_callback(call)
    elif data == 'mpx_ai':
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🤖 Send query: `/mpx your question`", parse_mode='Markdown')
    elif data == 'uptime':
        bot.answer_callback_query(call.id)
        uptime_str = get_uptime()
        bot.send_message(call.message.chat.id, f"⏱️ Uptime: `{uptime_str}`", parse_mode='Markdown')
    elif data.startswith('approve_'):
        handle_approve_callback(call)
    elif data.startswith('reject_'):
        handle_reject_callback(call)
    elif data.startswith('review_'):
        handle_review_callback(call)
    elif data == 'view_pending':
        if user_id in admin_ids:
            _logic_view_pending(call.message)
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ Admin only", show_alert=True)
    elif data.startswith('confirm_broadcast_'):
        handle_confirm_broadcast(call)
    elif data == 'cancel_broadcast':
        handle_cancel_broadcast(call)
    else:
        bot.answer_callback_query(call.id, "❌ Unknown action")

def upload_callback(call):
    user_id = call.from_user.id
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "∞"
        bot.answer_callback_query(call.id, f"❌ Limit reached ({current_files}/{limit_str})", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📤 Send your `.py`, `.js`, or `.zip` file")

def check_files_callback(call):
    _logic_check_files(call.message)
    bot.answer_callback_query(call.id)

def file_control_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "❌ You can only manage your own files", show_alert=True)
            return

        is_running = is_bot_running(script_owner_id, file_name)
        bot.answer_callback_query(call.id)
        
        file_info = f"""
╔════════════════════════════╗
║     📁 FILE CONTROLS        ║
╠════════════════════════════╣
║ 📄 {file_name}
║ 🔄 Status: {"🟢 RUNNING" if is_running else "⚪ STOPPED"}
╚════════════════════════════╝
"""
        bot.edit_message_text(file_info, call.message.chat.id, call.message.message_id,
                             reply_markup=create_control_buttons(script_owner_id, file_name, is_running),
                             parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in file_control_callback: {e}")

def start_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "❌ Permission denied", show_alert=True)
            return

        file_status = get_file_status(script_owner_id, file_name)
        if file_status['status'] != FILE_STATUS_APPROVED:
            bot.answer_callback_query(call.id, f"❌ File not approved! Status: {file_status['status']}", show_alert=True)
            return

        if is_bot_running(script_owner_id, file_name):
            bot.answer_callback_query(call.id, "⚠️ Already running", show_alert=True)
            return

        user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name)
        file_info = next((f for f in user_files.get(script_owner_id, []) if f[0] == file_name), None)
        
        if not file_info or not os.path.exists(file_path):
            bot.answer_callback_query(call.id, "❌ File not found", show_alert=True)
            return

        bot.answer_callback_query(call.id, f"▶️ Starting {file_name}...")
        
        if file_info[1] == 'py':
            threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        else:
            threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        
        time.sleep(1)
        is_now_running = is_bot_running(script_owner_id, file_name)
        status_text = "✅ RUNNING" if is_now_running else "⚠️ STARTING..."
        bot.edit_message_text(f"📁 {file_name}\n🟢 {status_text}", 
                             call.message.chat.id, call.message.message_id,
                             reply_markup=create_control_buttons(script_owner_id, file_name, is_now_running),
                             parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in start_bot_callback: {e}")
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)

def stop_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "❌ Permission denied", show_alert=True)
            return

        script_key = f"{script_owner_id}_{file_name}"
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]
        
        bot.answer_callback_query(call.id, f"🛑 Stopped {file_name}")
        bot.edit_message_text(f"📁 {file_name}\n⚪ STOPPED",
                             call.message.chat.id, call.message.message_id,
                             reply_markup=create_control_buttons(script_owner_id, file_name, False),
                             parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in stop_bot_callback: {e}")
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)

def restart_bot_callback(call):
    try:
        stop_bot_callback(call)
        time.sleep(1)
        start_bot_callback(call)
    except Exception as e:
        logger.error(f"Error in restart_bot_callback: {e}")

def delete_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "❌ Permission denied", show_alert=True)
            return

        markup = get_confirm_delete_buttons(script_owner_id, file_name)
        bot.answer_callback_query(call.id)
        bot.edit_message_text(f"🗑️ Delete `{file_name}`?\n\nThis cannot be undone!",
                             call.message.chat.id, call.message.message_id,
                             reply_markup=markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in delete_bot_callback: {e}")

def logs_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "❌ Permission denied", show_alert=True)
            return

        user_folder = get_user_folder(script_owner_id)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        
        if not os.path.exists(log_path):
            bot.answer_callback_query(call.id, "📜 No logs found", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            log_content = f.read()[-3500:]
        
        if not log_content.strip():
            log_content = "(Empty log)"
        
        bot.send_message(call.message.chat.id, f"📜 **Logs for `{file_name}`:**\n```\n{log_content}\n```", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in logs_bot_callback: {e}")
        bot.answer_callback_query(call.id, f"❌ Error reading logs", show_alert=True)

def status_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        file_status = get_file_status(script_owner_id, file_name)
        
        status_text = "✅ APPROVED" if file_status['status'] == FILE_STATUS_APPROVED else "⏳ PENDING" if file_status['status'] == FILE_STATUS_PENDING else "❌ REJECTED"
        
        response = f"📋 **File Status**\n\n📁 `{file_name}`\n📊 {status_text}"
        if file_status.get('reviewed_by'):
            response += f"\n👮 Reviewed by: `{file_status['reviewed_by']}`"
        
        bot.answer_callback_query(call.id, response, show_alert=True)
    except Exception as e:
        logger.error(f"Error in status_callback: {e}")

def speed_callback(call):
    _logic_bot_speed(call.message)
    bot.answer_callback_query(call.id)

def back_to_main_callback(call):
    user_id = call.from_user.id
    main_menu_text = f"👋 Welcome back, {call.from_user.first_name}!"
    bot.edit_message_text(main_menu_text, call.message.chat.id, call.message.message_id,
                         reply_markup=create_main_menu_inline(user_id), parse_mode='Markdown')
    bot.answer_callback_query(call.id)

def subscription_management_callback(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text("💳 **Subscription Management**",
                         call.message.chat.id, call.message.message_id,
                         reply_markup=create_subscription_menu(), parse_mode='Markdown')

def stats_callback(call):
    _logic_statistics(call.message)
    bot.answer_callback_query(call.id)

def lock_bot_callback(call):
    global bot_locked
    bot_locked = True
    bot.answer_callback_query(call.id, "🔒 Bot locked")
    back_to_main_callback(call)

def unlock_bot_callback(call):
    global bot_locked
    bot_locked = False
    bot.answer_callback_query(call.id, "🔓 Bot unlocked")
    back_to_main_callback(call)

def run_all_scripts_callback(call):
    _logic_run_all_scripts(call.message)
    bot.answer_callback_query(call.id)

def broadcast_init_callback(call):
    _logic_broadcast_init(call.message)
    bot.answer_callback_query(call.id)

def admin_panel_callback(call):
    _logic_admin_panel(call.message)
    bot.answer_callback_query(call.id)

def add_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "➕ Send User ID to add as Admin.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_add_admin_id)

def process_add_admin_id(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "❌ Owner only")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled")
        return
    try:
        new_admin_id = int(message.text.strip())
        if new_admin_id in admin_ids:
            bot.reply_to(message, f"⚠️ User `{new_admin_id}` is already Admin")
            return
        add_admin_db(new_admin_id)
        bot.reply_to(message, f"✅ User `{new_admin_id}` is now Admin!")
    except:
        bot.reply_to(message, "❌ Invalid ID")

def remove_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "➖ Send User ID to remove from Admin.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_admin_id)

def process_remove_admin_id(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "❌ Owner only")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled")
        return
    try:
        admin_id_remove = int(message.text.strip())
        if admin_id_remove == OWNER_ID:
            bot.reply_to(message, "❌ Cannot remove Owner")
            return
        if remove_admin_db(admin_id_remove):
            bot.reply_to(message, f"✅ Removed Admin `{admin_id_remove}`")
        else:
            bot.reply_to(message, f"⚠️ User `{admin_id_remove}` is not Admin")
    except:
        bot.reply_to(message, "❌ Invalid ID")

def list_admins_callback(call):
    admin_list = "\n".join([f"👑 `{aid}`" if aid == OWNER_ID else f"👮 `{aid}`" for aid in sorted(admin_ids)])
    bot.edit_message_text(f"📋 **Admins List**\n\n{admin_list}", 
                         call.message.chat.id, call.message.message_id,
                         reply_markup=create_admin_panel(), parse_mode='Markdown')
    bot.answer_callback_query(call.id)

def add_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "➕ Format: `USER_ID DAYS`\nExample: `123456789 30`\n/cancel to abort.", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_add_subscription)

def process_add_subscription(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "❌ Admin only")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled")
        return
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        days = int(parts[1])
        
        current_expiry = user_subscriptions.get(user_id, {}).get('expiry', datetime.now())
        if current_expiry < datetime.now():
            current_expiry = datetime.now()
        new_expiry = current_expiry + timedelta(days=days)
        save_subscription(user_id, new_expiry)
        
        bot.reply_to(message, f"✅ Added {days} days to `{user_id}`\n📅 Expires: {new_expiry.strftime('%Y-%m-%d')}")
    except:
        bot.reply_to(message, "❌ Invalid format. Use: `USER_ID DAYS`")

def remove_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "➖ Send User ID to remove subscription.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_subscription)

def process_remove_subscription(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "❌ Admin only")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled")
        return
    try:
        user_id = int(message.text.strip())
        remove_subscription_db(user_id)
        bot.reply_to(message, f"✅ Removed subscription for `{user_id}`")
    except:
        bot.reply_to(message, "❌ Invalid User ID")

def check_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔍 Send User ID to check subscription.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_check_subscription)

def process_check_subscription(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "❌ Admin only")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled")
        return
    try:
        user_id = int(message.text.strip())
        if user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now():
            expiry = user_subscriptions[user_id]['expiry']
            days_left = (expiry - datetime.now()).days
            bot.reply_to(message, f"✅ `{user_id}` has active subscription\n📅 Expires in {days_left} days")
        else:
            bot.reply_to(message, f"⚠️ `{user_id}` has NO active subscription")
    except:
        bot.reply_to(message, "❌ Invalid User ID")

def handle_approve_callback(call):
    try:
        admin_id = call.from_user.id
        if admin_id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ Admin only", show_alert=True)
            return
        
        _, user_id_str, file_name = call.data.split('_', 2)
        user_id = int(user_id_str)
        
        if update_file_status(user_id, file_name, FILE_STATUS_APPROVED, admin_id):
            bot.send_message(user_id, f"✅ **File Approved!**\n\n📁 `{file_name}`\nYou can now run this file.", parse_mode='Markdown')
            bot.answer_callback_query(call.id, "✅ Approved!")
            bot.edit_message_text(f"✅ APPROVED: {file_name}", call.message.chat.id, call.message.message_id)
    except Exception as e:
        logger.error(f"Error in approve: {e}")

def handle_reject_callback(call):
    try:
        admin_id = call.from_user.id
        if admin_id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ Admin only", show_alert=True)
            return
        
        _, user_id_str, file_name = call.data.split('_', 2)
        user_id = int(user_id_str)
        
        if update_file_status(user_id, file_name, FILE_STATUS_REJECTED, admin_id):
            bot.send_message(user_id, f"❌ **File Rejected!**\n\n📁 `{file_name}`\nReason: Malware detected.", parse_mode='Markdown')
            bot.answer_callback_query(call.id, "❌ Rejected!")
            bot.edit_message_text(f"❌ REJECTED: {file_name}", call.message.chat.id, call.message.message_id)
    except Exception as e:
        logger.error(f"Error in reject: {e}")

def handle_review_callback(call):
    try:
        admin_id = call.from_user.id
        if admin_id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ Admin only", show_alert=True)
            return
        
        _, user_id_str, file_name = call.data.split('_', 2)
        user_id = int(user_id_str)
        
        review_text = f"⚠️ **Review File**\n\n👤 User: `{user_id}`\n📁 File: `{file_name}`\n\nChoose action:"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Approve", callback_data=f'approve_{user_id}_{file_name}'),
            types.InlineKeyboardButton("❌ Reject", callback_data=f'reject_{user_id}_{file_name}')
        )
        bot.answer_callback_query(call.id)
        bot.edit_message_text(review_text, call.message.chat.id, call.message.message_id,
                             reply_markup=markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in review: {e}")

def _logic_view_pending(message):
    user_id = message.from_user.id
    if user_id not in admin_ids:
        bot.reply_to(message, "❌ Admin only")
        return
    
    pending_files = get_all_pending_files()
    if not pending_files:
        bot.reply_to(message, "✅ No pending files for approval")
        return
    
    response = "⚠️ **PENDING FILES (MALWARE DETECTED)**\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for idx, (uid, fname, ftype, utime) in enumerate(pending_files[:15], 1):
        response += f"{idx}. `{fname}` (User: {uid}, Type: {ftype})\n"
        markup.add(types.InlineKeyboardButton(f"{idx}. {fname}", callback_data=f'review_{uid}_{fname}'))
    
    if len(pending_files) > 15:
        response += f"\n... and {len(pending_files) - 15} more"
    
    markup.add(types.InlineKeyboardButton("🔄 Refresh", callback_data='view_pending'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    
    bot.reply_to(message, response, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['mpx'])
def handle_mpx_command(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "🔒 Bot locked")
        return

    if not message.text or len(message.text.split()) < 2:
        bot.reply_to(message, "🤖 Usage: `/mpx your question`", parse_mode='Markdown')
        return

    query = message.text.split(' ', 1)[1]
    bot.send_chat_action(message.chat.id, 'typing')

    try:
        headers = {"Authorization": f"Bearer {A4F_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": A4F_MODEL, "messages": [{"role": "user", "content": query}], "temperature": 0.7}
        response = requests.post(A4F_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        answer = result.get('choices', [{}])[0].get('message', {}).get('content', 'No response')
        
        if len(answer) > 4000:
            for x in range(0, len(answer), 4000):
                bot.reply_to(message, answer[x:x+4000], parse_mode='Markdown')
        else:
            bot.reply_to(message, answer, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message):
    _logic_send_welcome(message)

@bot.message_handler(commands=['pending'])
def command_pending(message):
    _logic_view_pending(message)

@bot.message_handler(func=lambda message: message.text in [btn for row in USER_MAIN_BUTTONS + ADMIN_MAIN_BUTTONS for btn in row])
def handle_button_text(message):
    text = message.text
    if text == "📢 ᴜᴘᴅᴀᴛᴇꜱ":
        _logic_updates_channel(message)
    elif text == "⏱️ ᴜᴘᴛɪᴍᴇ":
        _logic_uptime(message)
    elif text == "📊 ꜱᴛᴀᴛꜱ":
        _logic_statistics(message)
    elif text == "📤 ᴜᴘʟᴏᴀᴅ ꜰɪʟᴇ":
        _logic_upload_file(message)
    elif text == "📂 ᴍʏ ꜰɪʟᴇꜱ":
        _logic_check_files(message)
    elif text == "⚡ ʙᴏᴛ ꜱᴘᴇᴇᴅ":
        _logic_bot_speed(message)
    elif text == "🤖 ᴍᴘx ᴀɪ":
        bot.reply_to(message, "🤖 Send: `/mpx your question`", parse_mode='Markdown')
    elif text == "👤 ᴘʀᴏꜰɪʟᴇ":
        _logic_profile(message)
    elif text == "📞 ᴄᴏɴᴛᴀᴄᴛ":
        _logic_contact_owner(message)
    elif text == "🗑️ ᴅᴇʟᴇᴛᴇ ᴍᴀɴᴀɢᴇʀ":
        _logic_delete_manager(message)
    elif text == "🔍 ᴄʜᴇᴄᴋ ꜱᴛᴀᴛᴜꜱ":
        _logic_check_files(message)
    elif text == "🔄 ʀᴇꜰʀᴇꜱʜ":
        _logic_send_welcome(message)
    elif text == "ℹ️ ʜᴇʟᴘ":
        _logic_help(message)
    elif text in ["💳 ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴꜱ", "💳 ꜱᴜʙꜱ"]:
        _logic_subscriptions_panel(message)
    elif text == "📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ":
        _logic_broadcast_init(message)
    elif text == "🔒 ʟᴏᴄᴋ ʙᴏᴛ":
        _logic_toggle_lock_bot(message)
    elif text == "👑 ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ":
        _logic_admin_panel(message)
    elif text == "🟢 ʀᴜɴ ᴀʟʟ":
        _logic_run_all_scripts(message)
    elif text == "📋 ᴘᴇɴᴅɪɴɢ":
        _logic_view_pending(message)
    elif text == "🗑️ ᴅᴇʟᴇᴛᴇ ᴍɢʀ":
        _logic_delete_manager(message)
    else:
        _logic_send_welcome(message)

@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    user_id = message.from_user.id
    doc = message.document
    file_name = doc.file_name
    file_ext = os.path.splitext(file_name)[1].lower()
    
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "🔒 Bot locked")
        return
    
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "❌ Only `.py`, `.js`, `.zip` allowed")
        return
    
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "∞"
        bot.reply_to(message, f"❌ Limit reached ({current_files}/{limit_str})")
        return
    
    try:
        bot.reply_to(message, f"📥 Downloading `{file_name}`...", parse_mode='Markdown')
        file_info = bot.get_file(doc.file_id)
        file_content = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        
        if file_ext == '.zip':
            handle_zip_file(file_content, file_name, message)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f:
                f.write(file_content)
            
            if file_ext == '.py':
                handle_py_file(file_path, user_id, user_folder, file_name, message)
            elif file_ext == '.js':
                handle_js_file(file_path, user_id, user_folder, file_name, message)
    except Exception as e:
        logger.error(f"Error in file upload: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ==================== CLEANUP & MAIN ====================
def cleanup():
    logger.warning("Shutting down...")
    for key in list(bot_scripts.keys()):
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key])
    logger.warning("Cleanup done")

atexit.register(cleanup)

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    logging.info("✅ Flask server started")

if __name__ == '__main__':
    init_db()
    load_data()
    keep_alive()
    
    logger.info("="*50)
    logger.info("🤖 BOT STARTING WITH PREMIUM INTERFACE")
    logger.info(f"👑 Owner: {OWNER_ID}")
    logger.info(f"👮 Admins: {admin_ids}")
    logger.info("="*50)
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(10)