# H.py - COMPLETE BOT WITH ADVANCED MALWARE DETECTION + USER/FILE LISTS
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
import uuid
import math

from flask import Flask
from threading import Thread

# ====================== RENDER CONFIGURATION ======================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join('/tmp', 'upload_bots')
IROTECH_DIR = os.path.join('/tmp', 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# Flask app for Render
app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot is running on Render with Advanced Malware Detection!"

@app.route('/health')
def health():
    return json.dumps({'status': 'ok', 'uptime': get_uptime()})

# ========== CONFIGURATION (CHANGE THESE) ==========
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')          # <-- YOUR BOT TOKEN
OWNER_ID = int(os.environ.get('OWNER_ID', 8477195695))                      # <-- YOUR TELEGRAM ID
ADMIN_ID = int(os.environ.get('ADMIN_ID', 8477195695))                      # <-- SAME OR DIFFERENT
YOUR_USERNAME = os.environ.get('YOUR_USERNAME', '@yourusername')            # <-- YOUR USERNAME
UPDATE_CHANNEL = os.environ.get('UPDATE_CHANNEL', 'https://t.me/yourchannel')

ALLOWED_ADMIN_IDS = {OWNER_ID, ADMIN_ID}
ALLOWED_USERS = []   # empty = all users allowed

A4F_API_URL = "https://samuraiapi.in/v1/chat/completions"
A4F_API_KEY = "sk-NK6SS9tpWghyFJwkZLoCis1sMaF6RwQ5WF09mUoKKR0VKCm7"
A4F_MODEL = "provider10-claude-sonnet-4-20250514(clinesp)"

BOT_START_TIME = datetime.now()
FREE_USER_LIMIT = 2
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 99
OWNER_LIMIT = float('inf')

bot = telebot.TeleBot(TOKEN)

bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {OWNER_ID, ADMIN_ID}
bot_locked = False

# Admin permissions system (extended)
class AdminPermissions:
    def __init__(self):
        self.permissions = {
            'can_broadcast': {OWNER_ID, ADMIN_ID},
            'can_lock_bot': {OWNER_ID, ADMIN_ID},
            'can_manage_admins': {OWNER_ID},
            'can_approve_files': {OWNER_ID, ADMIN_ID},
            'can_run_all_scripts': {OWNER_ID, ADMIN_ID},
            'can_manage_subs': {OWNER_ID, ADMIN_ID},
            'can_view_pending': {OWNER_ID, ADMIN_ID},
            'can_see_admin_panel': {OWNER_ID, ADMIN_ID},
            'can_view_users': {OWNER_ID, ADMIN_ID},      # for /userslist
            'can_view_all_files': {OWNER_ID, ADMIN_ID},  # for /allfiles
        }
    
    def has_permission(self, user_id, permission):
        return user_id in self.permissions.get(permission, set())
    
    def add_admin_permission(self, admin_id, permission):
        if permission in self.permissions:
            self.permissions[permission].add(admin_id)
    
    def remove_admin_permission(self, admin_id, permission):
        if permission in self.permissions and admin_id != OWNER_ID:
            self.permissions[permission].discard(admin_id)

admin_permissions = AdminPermissions()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

FILE_STATUS_PENDING = "pending"
FILE_STATUS_APPROVED = "approved"
FILE_STATUS_REJECTED = "rejected"

# ==================== ENHANCED MALWARE DETECTION ====================
SUSPICIOUS_PATTERNS = [
    r'eval\s*\(', r'exec\s*\(', r'__import__\s*\(', r'os\.system\s*\(', r'subprocess\.call\s*\(',
    r'subprocess\.Popen\s*\(', r'os\.popen\s*\(', r'commands\.getoutput', r'Runtime\.exec',
    r'os\.remove\s*\(', r'shutil\.rmtree\s*\(', r'os\.unlink\s*\(', r'os\.rmdir\s*\(',
    r'socket\.socket', r'requests\.post', r'urllib\.request', r'http\.client', r'ftplib', r'telnetlib',
    r'base64\.b64decode', r'codecs\.decode', r'zlib\.decompress', r'sudo', r'chmod', r'chown', r'os\.setuid',
    r'\d{9,10}:AA[A-Za-z0-9_-]{33,}', r'crypto', r'miner', r'bitcoin', r'monero', r'pynput',
    r'keyboard\.record', r'GetAsyncKeyState', r'encrypt', r'decrypt', r'\.locked', r'ransom',
]

SAFE_PATTERNS = [
    r'print\s*\(', r'bot\.send_message', r'reply_to', r'telebot', r'flask', r'django',
    r'@bot\.message_handler', r'@app\.route',
]

def calculate_entropy(data):
    if not data:
        return 0
    entropy = 0
    for byte in set(data):
        p = data.count(byte) / len(data)
        entropy -= p * math.log2(p)
    return entropy

def is_obfuscated(content):
    # Long base64 strings
    if re.search(r'[A-Za-z0-9+/]{200,}=*', content):
        return True, "Large base64 string (>200 chars)"
    
    # Very long lines (>500 chars)
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if len(line) > 500:
            return True, f"Line {i+1} length {len(line)} (>500)"
    
    # High entropy (likely encrypted/obfuscated)
    entropy = calculate_entropy(content)
    if entropy > 5.5 and len(content) > 500:
        return True, f"High entropy ({entropy:.2f}) – possible encryption"
    
    # Low ASCII ratio (encoded data)
    ascii_ratio = sum(1 for c in content if 32 <= ord(c) <= 126) / max(len(content), 1)
    if ascii_ratio < 0.5:
        return True, f"Low ASCII ratio ({ascii_ratio:.2f}) – encoded content"
    
    return False, None

def scan_python_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        for pattern in SUSPICIOUS_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                is_safe = any(re.search(sp, content, re.IGNORECASE) for sp in SAFE_PATTERNS)
                if not is_safe:
                    return (True, f"Suspicious pattern: {pattern}")
        
        obfuscated, reason = is_obfuscated(content)
        if obfuscated:
            return (True, reason)
        
        return (False, "Clean")
    except Exception as e:
        logger.error(f"Python scan error: {e}")
        return (True, f"Scan error: {str(e)}")

def scan_javascript_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        js_suspicious = [
            r'eval\s*\(', r'Function\s*\(', r'child_process\.exec', r'require\s*\(\s*[\'"]child_process[\'"]\s*\)',
            r'process\.binding', r'vm\.runInNewContext', r'setTimeout\s*\(\s*[\'"].*[\'"]\s*,\s*\d+',
            r'atob\s*\(|btoa\s*\(', r'\\x[0-9a-fA-F]{2}',
        ]
        for pattern in js_suspicious:
            if re.search(pattern, content, re.IGNORECASE):
                return (True, f"Suspicious JS pattern: {pattern}")
        
        obfuscated, reason = is_obfuscated(content)
        if obfuscated:
            return (True, reason)
        
        return (False, "Clean")
    except Exception as e:
        return (True, f"JS scan error: {str(e)}")

def scan_zip_file(file_path):
    try:
        suspicious = []
        temp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(file_path, 'r') as zf:
            for member in zf.infolist():
                if member.filename.endswith(('.py', '.js')):
                    extracted = zf.extract(member, temp_dir)
                    ft = 'py' if member.filename.endswith('.py') else 'js'
                    is_mal, reason = scan_file_for_malware(extracted, ft)
                    if is_mal:
                        suspicious.append(f"{member.filename}: {reason}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        if suspicious:
            return (True, f"Suspicious files in ZIP: {', '.join(suspicious[:3])}")
        return (False, "Clean")
    except Exception as e:
        return (True, f"ZIP scan error: {str(e)}")

def scan_file_for_malware(file_path, file_type):
    if file_type == 'py':
        return scan_python_file(file_path)
    elif file_type == 'js':
        return scan_javascript_file(file_path)
    elif file_type == 'zip':
        return scan_zip_file(file_path)
    return (False, "Unknown")

# ==================== DATABASE FUNCTIONS ====================
DB_LOCK = threading.Lock()

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
        c.execute('''CREATE TABLE IF NOT EXISTS admin_permissions
                     (admin_id INTEGER, permission TEXT,
                      PRIMARY KEY (admin_id, permission))''')
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database init error: {e}", exc_info=True)

def get_uptime():
    uptime = datetime.now() - BOT_START_TIME
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

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
            logger.error(f"Error saving file approval: {e}")
        finally:
            conn.close()

def get_file_status(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''SELECT status, reviewed_by, review_time, file_type 
                        FROM file_approvals WHERE user_id=? AND file_name=?''', (user_id, file_name))
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
            c.execute('''UPDATE file_approvals SET status=?, reviewed_by=?, review_time=?
                        WHERE user_id=? AND file_name=?''', (status, admin_id, review_time, user_id, file_name))
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
                        FROM file_approvals WHERE status=? ORDER BY uploaded_time DESC''', (FILE_STATUS_PENDING,))
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
            logger.error(f"Error getting pending count: {e}")
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
        f"⚠️ **Malware detected or suspicious content**\n"
        f"🕐 **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"**Choose action:**"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f'approve_{user_id}_{file_name}'),
        types.InlineKeyboardButton("❌ Reject", callback_data=f'reject_{user_id}_{file_name}')
    )
    markup.add(types.InlineKeyboardButton("📋 View All Pending", callback_data='view_pending'))
    for admin_id in admin_ids:
        if admin_permissions.has_permission(admin_id, 'can_approve_files'):
            try:
                bot.forward_message(admin_id, message.chat.id, message.message_id)
                bot.send_message(admin_id, file_info, reply_markup=markup, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Failed to send approval to admin {admin_id}: {e}")

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
            logger.error(f"Error saving user file: {e}")
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
            logger.error(f"Error removing user file: {e}")
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

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except:
                pass
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
        logger.info(f"Data loaded: {len(active_users)} users, {len(user_subscriptions)} subs, {len(admin_ids)} admins.")
        # Load admin permissions from DB (simplified)
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT admin_id, permission FROM admin_permissions')
        for aid, perm in c.fetchall():
            admin_permissions.add_admin_permission(aid, perm)
        conn.close()
    except Exception as e:
        logger.error(f"Error loading data: {e}", exc_info=True)

def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID:
        return OWNER_LIMIT
    if user_id in admin_ids:
        return ADMIN_LIMIT
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
                if 'log_file' in script_info and script_info['log_file'] and not script_info['log_file'].closed:
                    try:
                        script_info['log_file'].close()
                    except:
                        pass
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            return False
        except Exception as e:
            logger.error(f"Error checking process: {e}")
            return False
    return False

def kill_process_tree(process_info):
    try:
        process = process_info.get('process')
        if process and hasattr(process, 'pid') and process.pid:
            try:
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except:
                        pass
                gone, alive = psutil.wait_procs(children, timeout=1)
                for p in alive:
                    try:
                        p.kill()
                    except:
                        pass
                try:
                    parent.terminate()
                    parent.wait(timeout=1)
                except:
                    parent.kill()
            except psutil.NoSuchProcess:
                pass
        if 'log_file' in process_info and process_info['log_file'] and not process_info['log_file'].closed:
            try:
                process_info['log_file'].close()
            except:
                pass
    except Exception as e:
        logger.error(f"Error killing process tree: {e}")

# ==================== RUN SCRIPT FUNCTIONS ====================
def run_script(script_path, script_owner_id, user_folder, file_name, message_obj, attempt=1):
    file_status = get_file_status(script_owner_id, file_name)
    if file_status['status'] != FILE_STATUS_APPROVED:
        bot.reply_to(message_obj, f"❌ File `{file_name}` not approved yet. Status: {file_status['status']}", parse_mode='Markdown')
        return
    script_key = f"{script_owner_id}_{file_name}"
    if is_bot_running(script_owner_id, file_name):
        bot.reply_to(message_obj, f"Script `{file_name}` already running.", parse_mode='Markdown')
        return
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        process = subprocess.Popen(
            [sys.executable, script_path], cwd=user_folder,
            stdout=log_file, stderr=log_file, stdin=subprocess.PIPE,
            encoding='utf-8', errors='ignore'
        )
        bot_scripts[script_key] = {
            'process': process, 'log_file': log_file, 'file_name': file_name,
            'chat_id': message_obj.chat.id, 'script_owner_id': script_owner_id,
            'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'py', 'script_key': script_key
        }
        bot.reply_to(message_obj, f"✅ Python script `{file_name}` started (PID: {process.pid})", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message_obj, f"Error starting script: {e}")

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj, attempt=1):
    file_status = get_file_status(script_owner_id, file_name)
    if file_status['status'] != FILE_STATUS_APPROVED:
        bot.reply_to(message_obj, f"❌ JS File `{file_name}` not approved yet. Status: {file_status['status']}", parse_mode='Markdown')
        return
    script_key = f"{script_owner_id}_{file_name}"
    if is_bot_running(script_owner_id, file_name):
        bot.reply_to(message_obj, f"JS script `{file_name}` already running.", parse_mode='Markdown')
        return
    try:
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        process = subprocess.Popen(
            ['node', script_path], cwd=user_folder,
            stdout=log_file, stderr=log_file, stdin=subprocess.PIPE,
            encoding='utf-8', errors='ignore'
        )
        bot_scripts[script_key] = {
            'process': process, 'log_file': log_file, 'file_name': file_name,
            'chat_id': message_obj.chat.id, 'script_owner_id': script_owner_id,
            'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'js', 'script_key': script_key
        }
        bot.reply_to(message_obj, f"✅ JS script `{file_name}` started (PID: {process.pid})", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message_obj, f"Error starting JS script: {e}")

# ==================== FILE HANDLERS (with enhanced malware detection) ====================
def handle_py_file(file_path, script_owner_id, user_folder, file_name, message):
    is_malicious, reason = scan_file_for_malware(file_path, 'py')
    if is_malicious:
        logger.warning(f"Malware detected in {file_name} from {script_owner_id}: {reason}")
        save_user_file(script_owner_id, file_name, 'py')
        save_file_approval(script_owner_id, file_name, 'py', FILE_STATUS_PENDING)
        send_file_for_approval(message, script_owner_id, file_name, 'py')
        bot.reply_to(message,
                    f"⚠️ **Security Warning!**\nFile `{file_name}` contains suspicious code.\n"
                    f"🔍 Reason: {reason}\n📋 Status: **PENDING ADMIN REVIEW**",
                    parse_mode='Markdown')
    else:
        save_user_file(script_owner_id, file_name, 'py')
        save_file_approval(script_owner_id, file_name, 'py', FILE_STATUS_APPROVED, script_owner_id)
        bot.reply_to(message, f"✅ File `{file_name}` scanned and **CLEAN**!\nAuto‑approved. You can now run it.", parse_mode='Markdown')
        for aid in admin_ids:
            if admin_permissions.has_permission(aid, 'can_approve_files'):
                try:
                    bot.send_message(aid, f"📋 Auto‑approved: `{file_name}` by user `{script_owner_id}`", parse_mode='Markdown')
                except:
                    pass

def handle_js_file(file_path, script_owner_id, user_folder, file_name, message):
    is_malicious, reason = scan_file_for_malware(file_path, 'js')
    if is_malicious:
        save_user_file(script_owner_id, file_name, 'js')
        save_file_approval(script_owner_id, file_name, 'js', FILE_STATUS_PENDING)
        send_file_for_approval(message, script_owner_id, file_name, 'js')
        bot.reply_to(message,
                    f"⚠️ **JS Security Warning!**\nFile `{file_name}` suspicious.\nReason: {reason}\nPending admin review.",
                    parse_mode='Markdown')
    else:
        save_user_file(script_owner_id, file_name, 'js')
        save_file_approval(script_owner_id, file_name, 'js', FILE_STATUS_APPROVED, script_owner_id)
        bot.reply_to(message, f"✅ JS File `{file_name}` clean → auto‑approved.", parse_mode='Markdown')

def handle_zip_file(downloaded_content, zip_name, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, zip_name)
    try:
        with open(zip_path, 'wb') as f:
            f.write(downloaded_content)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(temp_dir)
        # Find main script
        py_files = [f for f in os.listdir(temp_dir) if f.endswith('.py')]
        js_files = [f for f in os.listdir(temp_dir) if f.endswith('.js')]
        main_script = None
        file_type = None
        for p in ['main.py', 'bot.py', 'app.py']:
            if p in py_files:
                main_script = p
                file_type = 'py'
                break
        if not main_script and py_files:
            main_script = py_files[0]
            file_type = 'py'
        elif not main_script and js_files:
            main_script = js_files[0]
            file_type = 'js'
        if not main_script:
            bot.reply_to(message, "No .py or .js file found in zip.")
            return
        # Move files to user_folder
        for item in os.listdir(temp_dir):
            dest = os.path.join(user_folder, item)
            if os.path.exists(dest):
                if os.path.isdir(dest):
                    shutil.rmtree(dest)
                else:
                    os.remove(dest)
            shutil.move(os.path.join(temp_dir, item), dest)
        script_path = os.path.join(user_folder, main_script)
        is_mal, reason = scan_file_for_malware(script_path, file_type)
        save_user_file(user_id, main_script, file_type)
        if is_mal:
            save_file_approval(user_id, main_script, file_type, FILE_STATUS_PENDING)
            send_file_for_approval(message, user_id, main_script, file_type)
            bot.reply_to(message,
                        f"⚠️ Zip contains suspicious file `{main_script}`.\nReason: {reason}\nPending admin review.",
                        parse_mode='Markdown')
        else:
            save_file_approval(user_id, main_script, file_type, FILE_STATUS_APPROVED, user_id)
            bot.reply_to(message, f"✅ Zip extracted, main script `{main_script}` clean → auto‑approved.", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"Error processing zip: {str(e)}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== ADMIN COMMANDS ====================
@bot.message_handler(commands=['userslist'])
def cmd_list_users(message):
    user_id = message.from_user.id
    if user_id not in admin_ids or not admin_permissions.has_permission(user_id, 'can_view_users'):
        bot.reply_to(message, "❌ Admin permission required.")
        return
    if not active_users:
        bot.reply_to(message, "No active users found.")
        return
    response = "👥 **All Users**\n\n"
    for uid in sorted(active_users):
        try:
            chat = bot.get_chat(uid)
            username = f"@{chat.username}" if chat.username else "No username"
            first_name = chat.first_name or "N/A"
        except:
            username = "Unknown"
            first_name = "Unknown"
        sub_status = "Premium" if uid in user_subscriptions and user_subscriptions[uid]['expiry'] > datetime.now() else "Free"
        file_count = len(user_files.get(uid, []))
        response += f"• **ID:** `{uid}` | {first_name} | {username}\n   Sub: {sub_status} | Files: {file_count}\n\n"
        if len(response) > 3800:
            bot.reply_to(message, response, parse_mode='Markdown')
            response = ""
    if response:
        bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['allfiles'])
def cmd_all_files(message):
    user_id = message.from_user.id
    if user_id not in admin_ids or not admin_permissions.has_permission(user_id, 'can_view_all_files'):
        bot.reply_to(message, "❌ Admin permission required.")
        return
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, file_name, file_type FROM user_files")
    all_files = c.fetchall()
    conn.close()
    if not all_files:
        bot.reply_to(message, "No files have been uploaded yet.")
        return
    response = "📁 **All Uploaded Files**\n\n"
    for uid, fname, ftype in sorted(all_files, key=lambda x: x[0]):
        status = get_file_status(uid, fname)['status']
        status_icon = "✅" if status == 'approved' else "⚠️" if status == 'pending' else "❌"
        response += f"{status_icon} `{fname}` ({ftype}) – User `{uid}`\n"
        if len(response) > 3900:
            bot.reply_to(message, response, parse_mode='Markdown')
            response = ""
    if response:
        bot.reply_to(message, response, parse_mode='Markdown')

# ==================== ORIGINAL MESSAGE HANDLERS ====================
def is_authorized_user(user_id):
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS or user_id in admin_ids

def create_reply_keyboard_main_menu(user_id):
    show_admin = (user_id in admin_ids and user_id in ALLOWED_ADMIN_IDS) or user_id == OWNER_ID
    layout = [
        ["📢 Updates Channel", "⏱ Uptime"],
        ["📤 Upload File", "📂 Check Files"],
        ["⚡ Bot Speed", "📊 Statistics"],
        ["📞 Contact Owner", "🤖 MPX Ai"]
    ]
    if show_admin:
        layout.insert(2, ["💳 Subscriptions", "📢 Broadcast"])
        layout.insert(3, ["🔒 Lock Bot", "🟢 Run All Scripts"])
        layout.append(["👑 Admin Panel"])
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for row in layout:
        markup.add(*[types.KeyboardButton(text) for text in row])
    return markup

def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    if not is_authorized_user(user_id):
        bot.send_message(chat_id, "❌ Unauthorized access.")
        return
    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "Bot locked by admin.")
        return
    add_active_user(user_id)
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    welcome_msg = f"Welcome {user_name}!\nFiles: {current_files}/{limit_str}\nSend .py, .js, or .zip files."
    bot.send_message(chat_id, welcome_msg, reply_markup=create_reply_keyboard_main_menu(user_id))

def _logic_updates_channel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 Updates Channel", url=UPDATE_CHANNEL))
    bot.reply_to(message, "Visit our channel:", reply_markup=markup)

def _logic_upload_file(message):
    bot.reply_to(message, "Send your .py, .js, or .zip file.\n🛡️ Malware scan active.")

def _logic_check_files(message):
    user_id = message.from_user.id
    files = user_files.get(user_id, [])
    if not files:
        bot.reply_to(message, "No files.")
        return
    response = "Your files:\n"
    for fn, ft in files:
        status = get_file_status(user_id, fn)['status']
        icon = "✅" if status == 'approved' else "⚠️" if status == 'pending' else "❌"
        response += f"{icon} `{fn}` ({ft})\n"
    bot.reply_to(message, response, parse_mode='Markdown')

def _logic_bot_speed(message):
    start = time.time()
    bot.send_chat_action(message.chat.id, 'typing')
    latency = round((time.time() - start) * 1000, 2)
    bot.reply_to(message, f"Pong! {latency} ms")

def _logic_contact_owner(message):
    bot.reply_to(message, f"Contact: {YOUR_USERNAME}")

def _logic_uptime(message):
    bot.reply_to(message, f"Uptime: {get_uptime()}")

def _logic_statistics(message):
    total_users = len(active_users)
    total_files = sum(len(f) for f in user_files.values())
    running = sum(1 for k in list(bot_scripts.keys()) if is_bot_running(*k.split('_',1)[0], bot_scripts[k]['file_name']))
    bot.reply_to(message, f"Users: {total_users}\nFiles: {total_files}\nRunning: {running}")

def _logic_subscriptions_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "Admin only.")
        return
    bot.reply_to(message, "Subscription mgmt. Use /start menu.")

def _logic_broadcast_init(message):
    if message.from_user.id not in admin_ids or not admin_permissions.has_permission(message.from_user.id, 'can_broadcast'):
        bot.reply_to(message, "No permission.")
        return
    msg = bot.reply_to(message, "Send broadcast message or /cancel")
    bot.register_next_step_handler(msg, process_broadcast_message)

def process_broadcast_message(message):
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    text = message.text
    if not text:
        bot.reply_to(message, "Text only broadcast.")
        return
    sent = 0
    for uid in list(active_users):
        try:
            bot.send_message(uid, text)
            sent += 1
            time.sleep(0.05)
        except:
            pass
    bot.reply_to(message, f"Broadcast sent to {sent} users.")

def _logic_toggle_lock_bot(message):
    if not admin_permissions.has_permission(message.from_user.id, 'can_lock_bot'):
        bot.reply_to(message, "No permission.")
        return
    global bot_locked
    bot_locked = not bot_locked
    bot.reply_to(message, f"Bot {'locked' if bot_locked else 'unlocked'}.")

def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids or not admin_permissions.has_permission(message.from_user.id, 'can_see_admin_panel'):
        bot.reply_to(message, "No permission.")
        return
    bot.reply_to(message, "Admin panel. Use buttons in /start menu.")

def _logic_run_all_scripts(message):
    if not admin_permissions.has_permission(message.from_user.id, 'can_run_all_scripts'):
        bot.reply_to(message, "No permission.")
        return
    bot.reply_to(message, "Starting all user scripts...")
    started = 0
    for uid, files in user_files.items():
        for fn, ft in files:
            if get_file_status(uid, fn)['status'] == 'approved' and not is_bot_running(uid, fn):
                fp = os.path.join(get_user_folder(uid), fn)
                if ft == 'py':
                    threading.Thread(target=run_script, args=(fp, uid, get_user_folder(uid), fn, message)).start()
                elif ft == 'js':
                    threading.Thread(target=run_js_script, args=(fp, uid, get_user_folder(uid), fn, message)).start()
                started += 1
                time.sleep(0.5)
    bot.reply_to(message, f"Started {started} scripts.")

def handle_mpx_command(message):
    query = message.text.replace('/mpx', '').strip()
    if not query:
        bot.reply_to(message, "Usage: /mpx <question>")
        return
    try:
        headers = {"Authorization": f"Bearer {A4F_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": A4F_MODEL, "messages": [{"role": "user", "content": query}]}
        resp = requests.post(A4F_API_URL, headers=headers, json=payload, timeout=15)
        answer = resp.json().get('choices', [{}])[0].get('message', {}).get('content', "No answer")
        bot.reply_to(message, answer[:4000])
    except Exception as e:
        bot.reply_to(message, f"API error: {e}")

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
    "🟢 Run All Scripts": _logic_run_all_scripts,
    "👑 Admin Panel": _logic_admin_panel,
    "🤖 MPX Ai": handle_mpx_command,
}

@bot.message_handler(func=lambda m: m.text in BUTTON_TEXT_TO_LOGIC)
def handle_button_text(message):
    BUTTON_TEXT_TO_LOGIC[message.text](message)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    _logic_send_welcome(message)

@bot.message_handler(commands=['mpx'])
def mpx_cmd(message):
    handle_mpx_command(message)

@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "Bot locked.")
        return
    doc = message.document
    if not doc.file_name:
        bot.reply_to(message, "No filename.")
        return
    ext = os.path.splitext(doc.file_name)[1].lower()
    if ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "Only .py, .js, .zip allowed.")
        return
    if get_user_file_count(user_id) >= get_user_file_limit(user_id):
        bot.reply_to(message, "File limit reached.")
        return
    try:
        file_info = bot.get_file(doc.file_id)
        content = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        file_path = os.path.join(user_folder, doc.file_name)
        with open(file_path, 'wb') as f:
            f.write(content)
        if ext == '.py':
            handle_py_file(file_path, user_id, user_folder, doc.file_name, message)
        elif ext == '.js':
            handle_js_file(file_path, user_id, user_folder, doc.file_name, message)
        elif ext == '.zip':
            handle_zip_file(content, doc.file_name, message)
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

# ==================== CALLBACK QUERY HANDLER ====================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data
    user_id = call.from_user.id
    if data.startswith('approve_'):
        _, uid_str, fname = data.split('_', 2)
        uid = int(uid_str)
        if user_id in admin_ids and admin_permissions.has_permission(user_id, 'can_approve_files'):
            update_file_status(uid, fname, FILE_STATUS_APPROVED, user_id)
            bot.answer_callback_query(call.id, "Approved.")
            bot.send_message(uid, f"✅ Your file `{fname}` has been approved.", parse_mode='Markdown')
        else:
            bot.answer_callback_query(call.id, "No permission.", show_alert=True)
    elif data.startswith('reject_'):
        _, uid_str, fname = data.split('_', 2)
        uid = int(uid_str)
        if user_id in admin_ids and admin_permissions.has_permission(user_id, 'can_approve_files'):
            update_file_status(uid, fname, FILE_STATUS_REJECTED, user_id)
            bot.answer_callback_query(call.id, "Rejected.")
            bot.send_message(uid, f"❌ Your file `{fname}` was rejected due to malware.", parse_mode='Markdown')
        else:
            bot.answer_callback_query(call.id, "No permission.", show_alert=True)
    elif data == 'view_pending':
        if user_id in admin_ids and admin_permissions.has_permission(user_id, 'can_view_pending'):
            pending = get_all_pending_files()
            if not pending:
                bot.send_message(call.message.chat.id, "No pending files.")
            else:
                txt = "Pending files:\n"
                for uid, fn, ft, _ in pending:
                    txt += f"`{fn}` from `{uid}`\n"
                bot.send_message(call.message.chat.id, txt, parse_mode='Markdown')
        else:
            bot.answer_callback_query(call.id, "No permission.", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "Unknown action.")

# ==================== FLASK KEEP-ALIVE & CLEANUP ====================
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    logging.info("Flask keep-alive started.")

def cleanup():
    logger.warning("Shutting down, stopping scripts...")
    for key in list(bot_scripts.keys()):
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key])
    logger.warning("Cleanup done.")
atexit.register(cleanup)

# ==================== MAIN ====================
if __name__ == '__main__':
    keep_alive()
    init_db()
    load_data()
    logger.info("Bot started with advanced malware detection + /userslist and /allfiles")
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(15)