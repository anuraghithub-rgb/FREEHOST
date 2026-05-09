# H.py - RENDER COMPATIBLE FIXED VERSION
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
    return json.dumps({'status': 'ok'})

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
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

bot = telebot.TeleBot(TOKEN, parse_mode=None)

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

DB_LOCK = threading.Lock()

def init_db():
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
        logger.info("Database initialized.")
    except Exception as e:
        logger.error(f"DB init error: {e}")

def load_data():
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
    except Exception as e:
        logger.error(f"Load data error: {e}")

init_db()
load_data()

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
            logger.error(f"Save file approval error: {e}")
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
                return {'status': result[0], 'reviewed_by': result[1], 
                        'review_time': result[2], 'file_type': result[3]}
            return {'status': FILE_STATUS_PENDING, 'file_type': 'unknown'}
        except:
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
        except:
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
        except:
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
        except:
            return 0
        finally:
            conn.close()

def send_file_for_approval(message, user_id, file_name, file_type):
    user = message.from_user
    file_info = (f"📄 **NEW FILE FOR APPROVAL**\n\n"
                 f"👤 **User:** {user.first_name}\n"
                 f"📛 **Username:** @{user.username or 'N/A'}\n"
                 f"🆔 **User ID:** `{user_id}`\n"
                 f"📁 **File:** `{file_name}`\n"
                 f"📊 **Type:** {file_type}\n"
                 f"🕐 **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f'approve_{user_id}_{file_name}'),
        types.InlineKeyboardButton("❌ Reject", callback_data=f'reject_{user_id}_{file_name}')
    )
    
    for admin_id in admin_ids:
        try:
            bot.forward_message(admin_id, message.chat.id, message.message_id)
            bot.send_message(admin_id, file_info, reply_markup=markup, parse_mode='Markdown')
            save_file_approval(user_id, file_name, file_type, FILE_STATUS_PENDING)
        except Exception as e:
            logger.error(f"Failed to send to admin {admin_id}: {e}")

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
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except:
            if script_key in bot_scripts:
                if 'log_file' in script_info and script_info['log_file'] and not script_info['log_file'].closed:
                    try: script_info['log_file'].close()
                    except: pass
                del bot_scripts[script_key]
            return False
    return False

def kill_process_tree(process_info):
    try:
        if 'log_file' in process_info and process_info['log_file'] and not process_info['log_file'].closed:
            try: process_info['log_file'].close()
            except: pass
        process = process_info.get('process')
        if process and hasattr(process, 'pid') and process.pid:
            try:
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    try: child.kill()
                    except: pass
                parent.kill()
            except:
                pass
    except:
        pass

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
        except:
            pass
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
        except:
            pass
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
        except:
            pass
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
        except:
            pass
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
        except:
            pass
        finally:
            conn.close()

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
    markup.add(*buttons)
    markup.add(types.InlineKeyboardButton('⏱ Uptime', callback_data='uptime'))
    return markup

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row_buttons_text in layout_to_use:
        markup.add(*[types.KeyboardButton(text) for text in row_buttons_text])
    return markup

def create_control_buttons(script_owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.add(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{script_owner_id}_{file_name}')
        )
        markup.add(
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    else:
        markup.add(
            types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}')
        )
        markup.add(types.InlineKeyboardButton("📜 View Logs", callback_data=f'logs_{script_owner_id}_{file_name}'))
    
    markup.add(types.InlineKeyboardButton("🔙 Back to Files", callback_data='check_files'))
    return markup

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply):
    file_status = get_file_status(script_owner_id, file_name)
    if file_status['status'] != FILE_STATUS_APPROVED:
        bot.reply_to(message_obj_for_reply, f"❌ File `{file_name}` not approved yet! Status: {file_status['status']}")
        return
    
    script_key = f"{script_owner_id}_{file_name}"
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"Error: Script '{file_name}' not found!")
            remove_user_file_db(script_owner_id, file_name)
            return
        
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        
        process = subprocess.Popen(
            [sys.executable, script_path], cwd=user_folder, 
            stdout=log_file, stderr=log_file, stdin=subprocess.PIPE
        )
        
        bot_scripts[script_key] = {
            'process': process, 'log_file': log_file, 'file_name': file_name,
            'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id
        }
        bot.reply_to(message_obj_for_reply, f"✅ Script '{file_name}' started! (PID: {process.pid})")
    except Exception as e:
        logger.error(f"Error running script: {e}")
        bot.reply_to(message_obj_for_reply, f"Error: {str(e)}")

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply):
    file_status = get_file_status(script_owner_id, file_name)
    if file_status['status'] != FILE_STATUS_APPROVED:
        bot.reply_to(message_obj_for_reply, f"❌ File `{file_name}` not approved yet!")
        return
    
    script_key = f"{script_owner_id}_{file_name}"
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"Error: Script '{file_name}' not found!")
            remove_user_file_db(script_owner_id, file_name)
            return
        
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        
        process = subprocess.Popen(
            ['node', script_path], cwd=user_folder,
            stdout=log_file, stderr=log_file, stdin=subprocess.PIPE
        )
        
        bot_scripts[script_key] = {
            'process': process, 'log_file': log_file, 'file_name': file_name,
            'chat_id': message_obj_for_reply.chat.id, 'script_owner_id': script_owner_id, 'type': 'js'
        }
        bot.reply_to(message_obj_for_reply, f"✅ JS Script '{file_name}' started! (PID: {process.pid})")
    except Exception as e:
        logger.error(f"Error running JS script: {e}")
        bot.reply_to(message_obj_for_reply, f"Error: {str(e)}")

def handle_zip_file(downloaded_file_content, file_name_zip, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as f:
            f.write(downloaded_file_content)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
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
        
        if not main_script_name and py_files:
            main_script_name = py_files[0]
            file_type = 'py'
        elif not main_script_name and js_files:
            main_script_name = js_files[0]
            file_type = 'js'
        
        if not main_script_name:
            bot.reply_to(message, "No .py or .js script found in archive!")
            return
        
        for item_name in os.listdir(temp_dir):
            src_path = os.path.join(temp_dir, item_name)
            dest_path = os.path.join(user_folder, item_name)
            if os.path.exists(dest_path):
                if os.path.isdir(dest_path):
                    shutil.rmtree(dest_path)
                else:
                    os.remove(dest_path)
            shutil.move(src_path, dest_path)
        
        save_user_file(user_id, main_script_name, file_type)
        save_file_approval(user_id, main_script_name, file_type, FILE_STATUS_PENDING)
        send_file_for_approval(message, user_id, main_script_name, file_type)
        
        bot.reply_to(message, f"✅ Files extracted!\nMain: `{main_script_name}`\nStatus: PENDING APPROVAL", parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Zip error: {e}")
        bot.reply_to(message, f"Error processing zip: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

def handle_py_file(file_path, script_owner_id, user_folder, file_name, message):
    save_user_file(script_owner_id, file_name, 'py')
    save_file_approval(script_owner_id, file_name, 'py', FILE_STATUS_PENDING)
    send_file_for_approval(message, script_owner_id, file_name, 'py')
    bot.reply_to(message, f"✅ Python file `{file_name}` uploaded! Status: PENDING APPROVAL", parse_mode='Markdown')

def handle_js_file(file_path, script_owner_id, user_folder, file_name, message):
    save_user_file(script_owner_id, file_name, 'js')
    save_file_approval(script_owner_id, file_name, 'js', FILE_STATUS_PENDING)
    send_file_for_approval(message, script_owner_id, file_name, 'js')
    bot.reply_to(message, f"✅ JS file `{file_name}` uploaded! Status: PENDING APPROVAL", parse_mode='Markdown')

# ==================== BOT HANDLERS ====================

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "Bot locked by admin.")
        return
    
    if user_id not in active_users:
        add_active_user(user_id)
        try:
            bot.send_message(OWNER_ID, f"New user: {message.from_user.first_name} (ID: {user_id})")
        except:
            pass
    
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    
    welcome_msg = (f"Welcome, {message.from_user.first_name}!\n\n"
                   f"User ID: `{user_id}`\n"
                   f"Files: {current_files} / {file_limit}\n\n"
                   f"Upload Python (.py), JS (.js), or ZIP files.\n"
                   f"All files need admin approval first.")
    
    bot.reply_to(message, welcome_msg, reply_markup=create_reply_keyboard_main_menu(user_id), parse_mode='Markdown')

@bot.message_handler(commands=['mpx'])
def handle_mpx(message):
    if bot_locked and message.from_user.id not in admin_ids:
        bot.reply_to(message, "Bot locked.")
        return
    
    if not message.text or len(message.text.split()) < 2:
        bot.reply_to(message, "Usage: `/mpx Your question here`", parse_mode='Markdown')
        return
    
    query = message.text.split(' ', 1)[1]
    bot.send_chat_action(message.chat.id, 'typing')
    
    try:
        headers = {"Authorization": f"Bearer {A4F_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": A4F_MODEL, "messages": [{"role": "user", "content": query}], "temperature": 0.7}
        response = requests.post(A4F_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        answer = response.json().get('choices', [{}])[0].get('message', {}).get('content', 'No response')
        bot.reply_to(message, answer[:4000], parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}")

@bot.message_handler(commands=['ping'])
def ping(message):
    start = time.time()
    msg = bot.reply_to(message, "Pong!")
    latency = round((time.time() - start) * 1000, 2)
    bot.edit_message_text(f"Pong! {latency}ms", message.chat.id, msg.message_id)

@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    user_id = message.from_user.id
    
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "Bot locked.")
        return
    
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        bot.reply_to(message, f"File limit reached ({current_files}/{file_limit})")
        return
    
    doc = message.document
    file_name = doc.file_name
    if not file_name:
        bot.reply_to(message, "No file name!")
        return
    
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "Only .py, .js, .zip files allowed!")
        return
    
    try:
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        
        if file_ext == '.zip':
            handle_zip_file(downloaded, file_name, message)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f:
                f.write(downloaded)
            
            if file_ext == '.py':
                handle_py_file(file_path, user_id, user_folder, file_name, message)
            else:
                handle_js_file(file_path, user_id, user_folder, file_name, message)
                
    except Exception as e:
        logger.error(f"File upload error: {e}")
        bot.reply_to(message, f"Error: {str(e)}")

BUTTON_HANDLERS = {}

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text
    
    if text == "📢 Updates Channel":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('Join Channel', url=UPDATE_CHANNEL))
        bot.reply_to(message, "Updates Channel:", reply_markup=markup)
    
    elif text == "📤 Upload File":
        bot.reply_to(message, "Send your .py, .js, or .zip file")
    
    elif text == "📂 Check Files":
        user_files_list = user_files.get(user_id, [])
        if not user_files_list:
            bot.reply_to(message, "No files uploaded yet.")
            return
        
        response = "📁 Your Files:\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for file_name, file_type in user_files_list:
            btn_text = f"📄 {file_name} ({file_type})"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data='main_menu'))
        bot.reply_to(message, response, reply_markup=markup)
    
    elif text == "⚡ Bot Speed":
        start = time.time()
        bot.send_chat_action(message.chat.id, 'typing')
        latency = round((time.time() - start) * 1000, 2)
        bot.reply_to(message, f"⚡ Bot Speed: {latency}ms")
    
    elif text == "📊 Statistics":
        total_users = len(active_users)
        total_files = sum(len(files) for files in user_files.values())
        bot.reply_to(message, f"📊 Statistics:\nUsers: {total_users}\nFiles: {total_files}")
    
    elif text == "📞 Contact Owner":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('Contact', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
        bot.reply_to(message, "Contact Owner:", reply_markup=markup)
    
    elif text == "🤖 MPX Ai":
        bot.reply_to(message, "Send /mpx followed by your question")
    
    elif text == "⏱ Uptime":
        bot.reply_to(message, f"Uptime: {get_uptime()}")
    
    elif text == "🔒 Lock Bot" and user_id in admin_ids:
        global bot_locked
        bot_locked = True
        bot.reply_to(message, "🔒 Bot locked!")
    
    elif text == "🟢 Running All Code" and user_id in admin_ids:
        bot.reply_to(message, "Starting all scripts...")
        for uid, files in user_files.items():
            for fname, ftype in files:
                if get_file_status(uid, fname)['status'] == FILE_STATUS_APPROVED:
                    user_folder = get_user_folder(uid)
                    file_path = os.path.join(user_folder, fname)
                    if os.path.exists(file_path):
                        if ftype == 'py':
                            threading.Thread(target=run_script, args=(file_path, uid, user_folder, fname, message)).start()
                        else:
                            threading.Thread(target=run_js_script, args=(file_path, uid, user_folder, fname, message)).start()
        bot.reply_to(message, "Started all approved scripts!")
    
    elif text == "/ping":
        ping(message)
    
    else:
        bot.reply_to(message, "Use the buttons or /start")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data
    user_id = call.from_user.id
    
    if data == 'main_menu':
        bot.edit_message_text("Main Menu:", call.message.chat.id, call.message.message_id,
                              reply_markup=create_main_menu_inline(user_id))
    
    elif data.startswith('file_'):
        _, owner_id, file_name = data.split('_', 2)
        owner_id = int(owner_id)
        
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "You can only control your own files.", show_alert=True)
            return
        
        is_running = is_bot_running(owner_id, file_name)
        markup = create_control_buttons(owner_id, file_name, is_running)
        bot.edit_message_text(f"Controls for: {file_name}", call.message.chat.id, 
                             call.message.message_id, reply_markup=markup)
    
    elif data.startswith('start_'):
        _, owner_id, file_name = data.split('_', 2)
        owner_id = int(owner_id)
        
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Permission denied.", show_alert=True)
            return
        
        user_folder = get_user_folder(owner_id)
        file_path = os.path.join(user_folder, file_name)
        ftype = 'py' if file_name.endswith('.py') else 'js'
        
        if ftype == 'py':
            threading.Thread(target=run_script, args=(file_path, owner_id, user_folder, file_name, call.message)).start()
        else:
            threading.Thread(target=run_js_script, args=(file_path, owner_id, user_folder, file_name, call.message)).start()
        
        bot.answer_callback_query(call.id, f"Starting {file_name}...")
    
    elif data.startswith('stop_'):
        _, owner_id, file_name = data.split('_', 2)
        owner_id = int(owner_id)
        script_key = f"{owner_id}_{file_name}"
        
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]
            bot.answer_callback_query(call.id, f"Stopped {file_name}")
        else:
            bot.answer_callback_query(call.id, "Not running")
    
    elif data.startswith('restart_'):
        _, owner_id, file_name = data.split('_', 2)
        owner_id = int(owner_id)
        script_key = f"{owner_id}_{file_name}"
        
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]
            time.sleep(1)
        
        user_folder = get_user_folder(owner_id)
        file_path = os.path.join(user_folder, file_name)
        ftype = 'py' if file_name.endswith('.py') else 'js'
        
        if ftype == 'py':
            threading.Thread(target=run_script, args=(file_path, owner_id, user_folder, file_name, call.message)).start()
        else:
            threading.Thread(target=run_js_script, args=(file_path, owner_id, user_folder, file_name, call.message)).start()
        
        bot.answer_callback_query(call.id, f"Restarting {file_name}...")
    
    elif data.startswith('delete_'):
        _, owner_id, file_name = data.split('_', 2)
        owner_id = int(owner_id)
        script_key = f"{owner_id}_{file_name}"
        
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]
        
        user_folder = get_user_folder(owner_id)
        file_path = os.path.join(user_folder, file_name)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        remove_user_file_db(owner_id, file_name)
        bot.answer_callback_query(call.id, f"Deleted {file_name}")
        bot.edit_message_text(f"Deleted {file_name}", call.message.chat.id, call.message.message_id)
    
    elif data.startswith('logs_'):
        _, owner_id, file_name = data.split('_', 2)
        owner_id = int(owner_id)
        user_folder = get_user_folder(owner_id)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                log_content = f.read()[-3000:]
            bot.send_message(call.message.chat.id, f"Logs for {file_name}:\n```\n{log_content}\n```", parse_mode='Markdown')
        else:
            bot.answer_callback_query(call.id, "No logs found", show_alert=True)
    
    elif data.startswith('approve_'):
        if user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Admin only", show_alert=True)
            return
        
        _, uid, fname = data.split('_', 2)
        uid = int(uid)
        update_file_status(uid, fname, FILE_STATUS_APPROVED, user_id)
        bot.answer_callback_query(call.id, f"Approved {fname}")
        bot.edit_message_text(f"✅ APPROVED: {fname}", call.message.chat.id, call.message.message_id)
        
        try:
            bot.send_message(uid, f"✅ Your file `{fname}` has been approved! You can now run it.", parse_mode='Markdown')
        except:
            pass
    
    elif data.startswith('reject_'):
        if user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Admin only", show_alert=True)
            return
        
        _, uid, fname = data.split('_', 2)
        uid = int(uid)
        update_file_status(uid, fname, FILE_STATUS_REJECTED, user_id)
        bot.answer_callback_query(call.id, f"Rejected {fname}")
        bot.edit_message_text(f"❌ REJECTED: {fname}", call.message.chat.id, call.message.message_id)
        
        try:
            bot.send_message(uid, f"❌ Your file `{fname}` was rejected by admin.", parse_mode='Markdown')
        except:
            pass
    
    elif data == 'upload':
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Send your .py, .js, or .zip file")
    
    elif data == 'check_files':
        user_files_list = user_files.get(user_id, [])
        if not user_files_list:
            bot.answer_callback_query(call.id, "No files yet", show_alert=True)
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for fname, ftype in user_files_list:
            markup.add(types.InlineKeyboardButton(f"📄 {fname}", callback_data=f'file_{user_id}_{fname}'))
        markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='main_menu'))
        bot.edit_message_text("Your files:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif data == 'speed':
        start = time.time()
        latency = round((time.time() - start) * 1000, 2)
        bot.answer_callback_query(call.id, f"Speed: {latency}ms", show_alert=True)
    
    elif data == 'stats':
        total = len(active_users)
        files = sum(len(f) for f in user_files.values())
        bot.answer_callback_query(call.id, f"Users: {total} | Files: {files}", show_alert=True)
    
    elif data == 'uptime':
        bot.answer_callback_query(call.id, f"Uptime: {get_uptime()}", show_alert=True)
    
    elif data == 'mpx_ai':
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Use /mpx Your question")

# Flask server for Render
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    logger.info("Flask server started")

if __name__ == '__main__':
    keep_alive()
    logger.info("="*50)
    logger.info(f"Bot Started on Render!")
    logger.info(f"Owner ID: {OWNER_ID}")
    logger.info("="*50)
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)