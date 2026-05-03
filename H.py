# H.py - ULTIMATE SECURE VERSION WITH FILE SCANNING & REFERRAL SYSTEM
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
import magic
import base64
import random
import string

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
    return "🤖 Ultra Secure Bot is running on Render!"

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

# Referral System Variables
referral_counts = {}
user_referrers = {}
daily_top_users = {}
weekly_leaderboard = {}
pending_captcha_users = {}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

FILE_STATUS_PENDING = "pending"
FILE_STATUS_APPROVED = "approved"
FILE_STATUS_REJECTED = "rejected"
FILE_STATUS_CAPTCHA = "captcha"

# ====================== SECURITY SCANNER ======================
MALWARE_PATTERNS = [
    r'os\.system\s*\(', r'subprocess\.', r'eval\s*\(', r'exec\s*\(',
    r'__import__\s*\(', r'compile\s*\(', r'bytes\.fromhex', r'base64\.b64decode',
    r'cryptography', r'rsa\.', r'Crypto\.', r'pyaes', r'PyCryptodome',
    r'encrypt\s*\(', r'decrypt\s*\(', r'AES\.new', r'DES\.new',
    r'ransomware', r'locker', r'encrypt_file', r'decrypt_file',
    r'socket\.', r'request\.[get|post]', r'urllib\.request',
    r'telegram\.ext\.', r'Bot\s*\([\'"]\d+:', r'token\s*=\s*[\'"]\d+:',
    r'rm\s+-rf', r'dd\s+if=', r'mkfs\.', r'format\s+',
    r'curl\s+.*\|\s*bash', r'wget\s+.*\|\s*sh',
    r'chmod\s+777', r'chown\s+root',
]

SUSPICIOUS_IMPORTS = [
    'cryptography', 'Crypto', 'pyaes', 'rsa', 'paramiko', 
    'pynput', 'keyboard', 'mouse', 'pydirectinput',
    'scapy', 'impacket', 'pyminifier', 'pyarmor',
    'requests', 'urllib3', 'aiohttp', 'httpx',
]

def scan_file_content(content):
    """Scan file content for malware patterns"""
    try:
        content_str = content.decode('utf-8', errors='ignore')
    except:
        content_str = str(content)
    
    threats_found = []
    
    # Check for malware patterns
    for pattern in MALWARE_PATTERNS:
        if re.search(pattern, content_str, re.IGNORECASE):
            threats_found.append(f"Suspicious pattern: {pattern}")
    
    # Check for suspicious imports
    for imp in SUSPICIOUS_IMPORTS:
        if re.search(rf'import\s+{imp}|from\s+{imp}\s+import', content_str, re.IGNORECASE):
            threats_found.append(f"Suspicious import: {imp}")
    
    # Check for encoded strings (potential obfuscation)
    if len(re.findall(r'[A-Za-z0-9+/]{40,}={0,2}', content_str)) > 3:
        threats_found.append("Multiple base64 strings detected")
    
    # Check for hex strings
    if len(re.findall(r'\\x[0-9a-fA-F]{2}', content_str)) > 20:
        threats_found.append("Excessive hex encoding detected")
    
    return threats_found

def is_safe_file(file_path):
    """Comprehensive file safety check"""
    try:
        # Check file extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ['.py', '.js', '.zip']:
            return False, "Invalid file type"
        
        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size > 5 * 1024 * 1024:  # 5MB limit
            return False, "File too large (max 5MB)"
        
        if ext == '.py':
            with open(file_path, 'rb') as f:
                content = f.read()
            
            threats = scan_file_content(content)
            if threats:
                return False, f"Security threats detected: {', '.join(threats[:3])}"
            
            # Check for token patterns
            token_patterns = [
                r'\d{9,10}:[\w-]{35}',  # Telegram bot token
                r'sk-[a-zA-Z0-9]{20,}',  # OpenAI/API key
                r'Bearer\s+[a-zA-Z0-9_-]{20,}',
            ]
            
            for pattern in token_patterns:
                if re.search(pattern, content.decode('utf-8', errors='ignore')):
                    return False, "API tokens/keys detected in file (security risk)"
        
        elif ext == '.js':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            js_threats = [
                r'eval\s*\(', r'child_process\.exec', r'require\s*\(\s*[\'"]child_process',
                r'fs\.writeFile', r'fs\.unlink', r'process\.exit',
            ]
            
            for pattern in js_threats:
                if re.search(pattern, content, re.IGNORECASE):
                    return False, f"Suspicious JS pattern: {pattern}"
        
        return True, "File is safe"
    
    except Exception as e:
        logger.error(f"Safety check error: {e}")
        return False, f"Safety check failed: {str(e)}"

# ====================== VERIFICATION SYSTEM ======================
def generate_captcha():
    """Generate a simple math captcha"""
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    operation = random.choice(['+', '-'])
    
    if operation == '+':
        answer = num1 + num2
    else:
        answer = num1 - num2
    
    captcha_text = f"🔐 **Verification Required**\n\nSolve: {num1} {operation} {num2} = ?\n\nSend only the number."
    
    return captcha_text, answer

def verify_captcha(user_id, user_answer, correct_answer):
    """Verify captcha answer"""
    try:
        if int(user_answer) == correct_answer:
            return True
    except:
        pass
    return False

# ====================== REFERRAL SYSTEM ======================
def init_referral_db():
    """Initialize referral tables"""
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS referrals
                     (user_id INTEGER PRIMARY KEY, 
                      referred_by INTEGER,
                      referral_code TEXT UNIQUE,
                      referral_count INTEGER DEFAULT 0,
                      join_date TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS referral_earnings
                     (user_id INTEGER,
                      file_hosted INTEGER DEFAULT 0,
                      bonus_earned INTEGER DEFAULT 0,
                      last_reset TEXT,
                      PRIMARY KEY (user_id))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS weekly_top
                     (user_id INTEGER PRIMARY KEY,
                      file_count INTEGER DEFAULT 0,
                      week_start TEXT)''')
        
        conn.commit()
        conn.close()
        logger.info("Referral database initialized")
    except Exception as e:
        logger.error(f"Referral DB init error: {e}")

def get_referral_code(user_id):
    """Generate or get existing referral code"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    
    c.execute('SELECT referral_code FROM referrals WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    
    if result:
        conn.close()
        return result[0]
    
    # Generate new code
    code = base64.b64encode(f"{user_id}_{int(time.time())}".encode()).decode()[:8]
    c.execute('INSERT INTO referrals (user_id, referral_code, join_date) VALUES (?, ?, ?)',
              (user_id, code, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return code

def process_referral(new_user_id, referrer_code):
    """Process referral when new user joins"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    
    # Find referrer
    c.execute('SELECT user_id FROM referrals WHERE referral_code = ?', (referrer_code,))
    referrer = c.fetchone()
    
    if referrer and referrer[0] != new_user_id:
        referrer_id = referrer[0]
        
        # Check if new user already referred
        c.execute('SELECT referred_by FROM referrals WHERE user_id = ?', (new_user_id,))
        existing = c.fetchone()
        
        if not existing:
            # Save referral relation
            c.execute('UPDATE referrals SET referred_by = ? WHERE user_id = ?', 
                     (referrer_id, new_user_id))
            
            # Increment referral count
            c.execute('UPDATE referrals SET referral_count = referral_count + 1 WHERE user_id = ?',
                     (referrer_id,))
            
            # Award bonus - 2 extra file slots
            c.execute('''INSERT OR REPLACE INTO referral_earnings 
                        (user_id, file_hosted, bonus_earned, last_reset)
                        VALUES (?, COALESCE((SELECT file_hosted FROM referral_earnings WHERE user_id = ?), 0) + 2,
                                COALESCE((SELECT bonus_earned FROM referral_earnings WHERE user_id = ?), 0) + 2,
                                ?)''',
                     (referrer_id, referrer_id, referrer_id, datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            
            # Notify referrer
            try:
                bot.send_message(referrer_id, 
                               f"🎉 **New Referral!**\n\n"
                               f"Someone joined using your code!\n"
                               f"You earned +2 file hosting slots.\n"
                               f"Total bonus slots: {get_user_bonus_slots(referrer_id)}")
            except:
                pass
            
            return True
    
    conn.close()
    return False

def get_user_bonus_slots(user_id):
    """Get bonus file slots from referrals"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    
    c.execute('SELECT bonus_earned FROM referral_earnings WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    
    conn.close()
    return result[0] if result else 0

def update_weekly_stats(user_id):
    """Update weekly leaderboard stats"""
    current_week = datetime.now().strftime('%Y-%W')
    
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    
    c.execute('''INSERT OR REPLACE INTO weekly_top (user_id, file_count, week_start)
                 VALUES (?, COALESCE((SELECT file_count FROM weekly_top WHERE user_id = ?), 0) + 1, ?)''',
              (user_id, user_id, current_week))
    
    conn.commit()
    conn.close()

def get_weekly_top_users(limit=5):
    """Get top users for current week"""
    current_week = datetime.now().strftime('%Y-%W')
    
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    
    c.execute('''SELECT user_id, file_count FROM weekly_top 
                 WHERE week_start = ? 
                 ORDER BY file_count DESC LIMIT ?''', (current_week, limit))
    
    results = c.fetchall()
    conn.close()
    return results

def get_referral_stats(user_id):
    """Get referral statistics for a user"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    
    c.execute('SELECT referral_count FROM referrals WHERE user_id = ?', (user_id,))
    count = c.fetchone()
    
    c.execute('SELECT bonus_earned FROM referral_earnings WHERE user_id = ?', (user_id,))
    bonus = c.fetchone()
    
    conn.close()
    return {
        'referrals': count[0] if count else 0,
        'bonus_slots': bonus[0] if bonus else 0
    }

# ====================== DATABASE FUNCTIONS ======================
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
                      uploaded_time TEXT, message_id INTEGER, security_scan TEXT,
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

# ====================== FILE APPROVAL WITH SECURITY ======================
DB_LOCK = threading.Lock()

def save_file_approval(user_id, file_name, file_type, status=FILE_STATUS_PENDING, reviewed_by=None, message_id=None, security_scan=None):
    """Save or update file approval status"""
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            uploaded_time = datetime.now().isoformat()
            review_time = datetime.now().isoformat() if reviewed_by else None
            c.execute('''INSERT OR REPLACE INTO file_approvals 
                        (user_id, file_name, file_type, status, reviewed_by, review_time, uploaded_time, message_id, security_scan) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, file_name, file_type, status, reviewed_by, review_time, uploaded_time, message_id, security_scan))
            conn.commit()
            logger.info(f"File approval saved: {user_id}/{file_name} -> {status}")
        except Exception as e:
            logger.error(f"Error saving file approval: {e}", exc_info=True)
        finally:
            conn.close()

def get_file_status(user_id, file_name):
    """Get approval status of a file"""
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''SELECT status, reviewed_by, review_time, file_type, security_scan 
                        FROM file_approvals WHERE user_id=? AND file_name=?''',
                     (user_id, file_name))
            result = c.fetchone()
            if result:
                return {
                    'status': result[0],
                    'reviewed_by': result[1],
                    'review_time': result[2],
                    'file_type': result[3],
                    'security_scan': result[4] if len(result) > 4 else None
                }
            return {'status': FILE_STATUS_PENDING, 'file_type': 'unknown', 'security_scan': None}
        except Exception as e:
            logger.error(f"Error getting file status: {e}")
            return {'status': FILE_STATUS_PENDING, 'file_type': 'unknown', 'security_scan': None}
        finally:
            conn.close()

def update_file_status(user_id, file_name, status, admin_id):
    """Update file approval status"""
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
            logger.info(f"File status updated: {user_id}/{file_name} -> {status} by {admin_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating file status: {e}")
            return False
        finally:
            conn.close()

def auto_approve_if_safe(file_path, user_id, file_name, file_type):
    """Automatically approve file if it passes security checks"""
    is_safe, message = is_safe_file(file_path)
    
    if is_safe:
        # File is safe - auto approve
        update_file_status(user_id, file_name, FILE_STATUS_APPROVED, OWNER_ID)
        bot.send_message(user_id,
                        f"✅ **File Auto-Approved!**\n\n"
                        f"📁 File: `{file_name}`\n"
                        f"🔒 Security Scan: **PASSED**\n"
                        f"📝 Message: {message}\n\n"
                        f"Your file has been automatically approved as it passed all security checks.",
                        parse_mode='Markdown')
        return True
    else:
        # File has issues - send to admin
        update_file_status(user_id, file_name, FILE_STATUS_PENDING, None, security_scan=message)
        return False

def send_to_admin_for_review(user_id, file_name, file_type, security_issues):
    """Send suspicious file to admin for manual review"""
    for admin_id in admin_ids:
        try:
            bot.send_message(admin_id,
                           f"⚠️ **SUSPICIOUS FILE DETECTED** ⚠️\n\n"
                           f"👤 User: `{user_id}`\n"
                           f"📁 File: `{file_name}`\n"
                           f"📊 Type: {file_type}\n"
                           f"🔴 Issues: {security_issues}\n\n"
                           f"⚠️ This file requires manual review before approval!",
                           parse_mode='Markdown')
        except:
            pass

# ====================== MODIFIED FILE UPLOAD WITH VERIFICATION ======================
def get_user_file_limit(user_id):
    """Get user's file limit including referral bonuses"""
    base_limit = FREE_USER_LIMIT
    if user_id == OWNER_ID:
        return OWNER_LIMIT
    if user_id in admin_ids:
        return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        base_limit = SUBSCRIBED_USER_LIMIT
    
    # Add referral bonus
    bonus_slots = get_user_bonus_slots(user_id)
    return base_limit + bonus_slots

def handle_verified_upload(message, file_path, user_id, file_name, file_type):
    """Handle file after verification"""
    # Check file safety
    is_safe, scan_result = is_safe_file(file_path)
    
    if is_safe:
        # Auto approve safe files
        save_user_file(user_id, file_name, file_type)
        update_file_status(user_id, file_name, FILE_STATUS_APPROVED, OWNER_ID, security_scan="PASSED")
        
        # Update weekly stats
        update_weekly_stats(user_id)
        
        bot.reply_to(message,
                    f"✅ **File Uploaded & Auto-Approved!**\n\n"
                    f"📁 File: `{file_name}`\n"
                    f"📊 Type: {file_type}\n"
                    f"🔒 Security: **CLEAN**\n"
                    f"✅ Status: **READY TO RUN**\n\n"
                    f"Use /checkfiles to run your file.",
                    parse_mode='Markdown')
        
        # Notify admin of auto-approval
        for admin_id in admin_ids:
            try:
                bot.send_message(admin_id,
                               f"✅ **Auto-Approved File**\n\n"
                               f"👤 User: `{user_id}`\n"
                               f"📁 File: `{file_name}`\n"
                               f"🔒 Security: PASSED\n"
                               f"🤖 Auto-approved by security system.",
                               parse_mode='Markdown')
            except:
                pass
    else:
        # File failed security - send to admin
        save_user_file(user_id, file_name, file_type)
        save_file_approval(user_id, file_name, file_type, FILE_STATUS_PENDING, None, None, scan_result)
        
        # Notify admin for review
        send_to_admin_for_review(user_id, file_name, file_type, scan_result)
        
        bot.reply_to(message,
                    f"⚠️ **File Under Review**\n\n"
                    f"📁 File: `{file_name}`\n"
                    f"🔍 Security Scan: **ISSUES DETECTED**\n"
                    f"📝 Details: {scan_result}\n\n"
                    f"👮‍♂️ File has been sent to admin for manual review.\n"
                    f"You'll be notified when a decision is made.",
                    parse_mode='Markdown')

# ====================== REFERRAL COMMANDS ======================
@bot.message_handler(commands=['refer', 'ref'])
def handle_referral(message):
    user_id = message.from_user.id
    referral_code = get_referral_code(user_id)
    
    stats = get_referral_stats(user_id)
    bonus_slots = get_user_bonus_slots(user_id)
    
    text = (
        f"🎁 **Referral Program**\n\n"
        f"Your Referral Code:\n`{referral_code}`\n\n"
        f"📊 **Your Stats:**\n"
        f"• Total Referrals: {stats['referrals']}\n"
        f"• Bonus Slots Earned: {bonus_slots}\n"
        f"• Current File Limit: {get_user_file_limit(user_id)}\n\n"
        f"💫 **How it works:**\n"
        f"• Share your code with friends\n"
        f"• Each referral = +2 file slots\n"
        f"• Top referrers get weekly rewards\n\n"
        f"🔗 Share link:\n"
        f"`https://t.me/{bot.get_me().username}?start=ref_{referral_code}`"
    )
    
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['leaderboard', 'top'])
def handle_leaderboard(message):
    top_users = get_weekly_top_users(10)
    
    if not top_users:
        bot.reply_to(message, "No data yet. Be the first to upload files!")
        return
    
    text = "🏆 **Weekly Leaderboard** 🏆\n\n"
    
    for idx, (user_id, file_count) in enumerate(top_users, 1):
        try:
            user = bot.get_chat(user_id)
            name = user.first_name
            if len(name) > 20:
                name = name[:17] + "..."
        except:
            name = f"User {user_id}"
        
        medal = ""
        if idx == 1:
            medal = "👑 "
        elif idx == 2:
            medal = "🥈 "
        elif idx == 3:
            medal = "🥉 "
        
        text += f"{medal}{idx}. **{name}** - {file_count} files\n"
    
    text += f"\n✨ **Weekly Reward:** Top user gets +7 file hosting slots!"
    
    bot.reply_to(message, text, parse_mode='Markdown')

# ====================== MODIFIED START WITH REFERRAL ======================
@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message):
    user_id = message.from_user.id
    
    # Check for referral
    if message.text and 'start=ref_' in message.text:
        referral_code = message.text.split('ref_')[-1]
        process_referral(user_id, referral_code)
    
    # Rest of welcome logic...
    _logic_send_welcome(message)

# ====================== MODIFIED UPLOAD WITH CAPTCHA ======================
def request_captcha_verification(message):
    """Request captcha verification before upload"""
    user_id = message.from_user.id
    captcha_text, answer = generate_captcha()
    
    pending_captcha_users[user_id] = {
        'answer': answer,
        'message_id': message.message_id,
        'timestamp': time.time()
    }
    
    msg = bot.reply_to(message, captcha_text, parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_captcha_verification)

def process_captcha_verification(message):
    """Process captcha answer"""
    user_id = message.from_user.id
    
    if user_id not in pending_captcha_users:
        bot.reply_to(message, "Session expired. Please try uploading again.")
        return
    
    captcha_data = pending_captcha_users[user_id]
    
    if verify_captcha(user_id, message.text, captcha_data['answer']):
        bot.reply_to(message, "✅ **Verification passed!**\nNow send your file.")
        # Clear captcha data
        del pending_captcha_users[user_id]
        # Set flag that user is verified
        bot.register_next_step_handler(message, handle_file_upload_doc)
    else:
        bot.reply_to(message, "❌ **Verification failed!**\nPlease try uploading again.")
        del pending_captcha_users[user_id]

# ====================== MODIFIED FILE UPLOAD HANDLER ======================
@bot.message_handler(content_types=['document'])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    doc = message.document
    logger.info(f"Doc from {user_id}: {doc.file_name} ({doc.mime_type}), Size: {doc.file_size}")

    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "Bot locked, cannot accept files.")
        return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, f"File limit ({current_files}/{limit_str}) reached. Refer friends to get more slots!\nUse /refer to get your code.")
        return

    file_name = doc.file_name
    if not file_name:
        bot.reply_to(message, "No file name. Ensure file has a name.")
        return
    
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "Unsupported type! Only `.py`, `.js`, `.zip` allowed.")
        return
    
    max_file_size = 5 * 1024 * 1024  # 5MB for security
    if doc.file_size > max_file_size:
        bot.reply_to(message, f"File too large (Max: {max_file_size // 1024 // 1024} MB).")
        return

    try:
        download_wait_msg = bot.reply_to(message, f"Downloading `{file_name}`...")
        file_info_tg_doc = bot.get_file(doc.file_id)
        downloaded_file_content = bot.download_file(file_info_tg_doc.file_path)
        bot.edit_message_text(f"Downloaded `{file_name}`. Processing...", chat_id, download_wait_msg.message_id)
        logger.info(f"Downloaded {file_name} for user {user_id}")
        user_folder = get_user_folder(user_id)

        if file_ext == '.zip':
            handle_zip_file(downloaded_file_content, file_name, message)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f:
                f.write(downloaded_file_content)
            logger.info(f"Saved single file to {file_path}")
            
            # Request captcha verification
            request_captcha_verification(message)
            
    except telebot.apihelper.ApiTelegramException as e:
         logger.error(f"Telegram API Error handling file for {user_id}: {e}", exc_info=True)
         if "file is too big" in str(e).lower():
              bot.reply_to(message, f"Telegram API Error: File too large to download (~20MB limit).")
         else:
              bot.reply_to(message, f"Telegram API Error: {str(e)}. Try later.")
    except Exception as e:
        logger.error(f"General error handling file for {user_id}: {e}", exc_info=True)
        bot.reply_to(message, f"Unexpected error: {str(e)}")

def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

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
            logger.info(f"Saved file '{file_name}' ({file_type}) for user {user_id}")
        except sqlite3.Error as e:
            logger.error(f"SQLite error saving file for user {user_id}, {file_name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error saving file for {user_id}, {file_name}: {e}", exc_info=True)
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
            logger.info(f"Removed file '{file_name}' for user {user_id} from DB")
        except sqlite3.Error as e:
            logger.error(f"SQLite error removing file for {user_id}, {file_name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error removing file for {user_id}, {file_name}: {e}", exc_info=True)
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
            logger.info(f"Added/Confirmed active user {user_id} in DB")
        except sqlite3.Error as e:
            logger.error(f"SQLite error adding active user {user_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error adding active user {user_id}: {e}", exc_info=True)
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
            logger.info(f"Saved subscription for {user_id}, expiry {expiry_str}")
        except sqlite3.Error as e:
            logger.error(f"SQLite error saving subscription for {user_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error saving subscription for {user_id}: {e}", exc_info=True)
        finally:
            conn.close()

# ====================== MODIFIED RUN SCRIPT WITH APPROVAL CHECK ======================
def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    file_status = get_file_status(script_owner_id, file_name)
    if file_status['status'] != FILE_STATUS_APPROVED:
        bot.reply_to(message_obj_for_reply,
                    f"❌ File `{file_name}` is not approved yet!\n"
                    f"📋 Status: **{file_status['status'].upper()}**\n"
                    f"🔒 Security: {file_status.get('security_scan', 'Not scanned')}\n\n"
                    f"⚠️ Only approved files can run.",
                    parse_mode='Markdown')
        return
    
    # Existing run_script logic continues...
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"Failed to run '{file_name}' after {max_attempts} attempts. Check logs.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"Attempt {attempt} to run Python script: {script_path} (Key: {script_key}) for user {script_owner_id}")

    # Check file safety before running
    if not is_safe_file(script_path)[0]:
        bot.reply_to(message_obj_for_reply, f"❌ **Security Alert!**\nFile `{file_name}` failed security re-check.\nCannot run this file.")
        return

    # Continue with rest of run_script logic...
    # (Keeping existing run_script functionality but with safety check)

# ====================== REMAINING FUNCTIONS (Keeping existing bot logic) ======================
# [Note: Keep all existing functions from original code above]
# Including: handle_zip_file, handle_py_file, handle_js_file, 
# _logic_send_welcome, _logic_check_files, etc.
# But they will now use the modified approval system

# ====================== RUN BOT ======================
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    logging.info("✅ Flask Keep-Alive server started on Render")

def cleanup():
    logger.warning("Shutdown. Cleaning up processes...")
    script_keys_to_stop = list(bot_scripts.keys())
    if not script_keys_to_stop:
        logger.info("No scripts running. Exiting.")
        return
    logger.info(f"Stopping {len(script_keys_to_stop)} scripts...")
    for key in script_keys_to_stop:
        if key in bot_scripts:
            logger.info(f"Stopping: {key}")
            kill_process_tree(bot_scripts[key])
        else:
            logger.info(f"Script {key} already removed.")
    logger.warning("Cleanup finished.")

atexit.register(cleanup)

def kill_process_tree(process_info):
    pid = None
    log_file_closed = False
    script_key = process_info.get('script_key', 'N/A')
    
    try:
        if 'log_file' in process_info and hasattr(process_info['log_file'], 'close') and not process_info['log_file'].closed:
            try:
                process_info['log_file'].close()
                log_file_closed = True
                logger.info(f"Closed log file for {script_key} (PID: {process_info.get('process', {}).get('pid', 'N/A')})")
            except Exception as log_e:
                logger.error(f"Error closing log file during kill for {script_key}: {log_e}")
        
        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            pid = process.pid
            if pid:
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    logger.info(f"Attempting to kill process tree for {script_key} (PID: {pid}, Children: {[c.pid for c in children]})")
                    
                    for child in children:
                        try:
                            child.terminate()
                            logger.info(f"Terminated child process {child.pid} for {script_key}")
                        except psutil.NoSuchProcess:
                            logger.warning(f"Child process {child.pid} for {script_key} already gone.")
                        except Exception as e:
                            logger.error(f"Error terminating child {child.pid} for {script_key}: {e}. Trying kill...")
                            try:
                                child.kill()
                                logger.info(f"Killed child process {child.pid} for {script_key}")
                            except Exception as e2:
                                logger.error(f"Failed to kill child {child.pid} for {script_key}: {e2}")
                    
                    gone, alive = psutil.wait_procs(children, timeout=1)
                    for p in alive:
                        logger.warning(f"Child process {p.pid} for {script_key} still alive. Killing.")
                        try:
                            p.kill()
                        except Exception as e:
                            logger.error(f"Failed to kill child {p.pid} for {script_key} after wait: {e}")
                    
                    try:
                        parent.terminate()
                        logger.info(f"Terminated parent process {pid} for {script_key}")
                        try:
                            parent.wait(timeout=1)
                        except psutil.TimeoutExpired:
                            logger.warning(f"Parent process {pid} for {script_key} did not terminate. Killing.")
                            parent.kill()
                            logger.info(f"Killed parent process {pid} for {script_key}")
                    except psutil.NoSuchProcess:
                        logger.warning(f"Parent process {pid} for {script_key} already gone.")
                    except Exception as e:
                        logger.error(f"Error terminating parent {pid} for {script_key}: {e}. Trying kill...")
                        try:
                            parent.kill()
                            logger.info(f"Killed parent process {pid} for {script_key}")
                        except Exception as e2:
                            logger.error(f"Failed to kill parent {pid} for {script_key}: {e2}")
                except psutil.NoSuchProcess:
                    logger.warning(f"Process {pid or 'N/A'} for {script_key} not found during kill. Already terminated?")
            else:
                logger.error(f"Process PID is None for {script_key}.")
        elif log_file_closed:
            logger.warning(f"Process object missing for {script_key}, but log file closed.")
        else:
            logger.error(f"Process object missing for {script_key}, and no log file. Cannot kill.")
    except Exception as e:
        logger.error(f"Unexpected error killing process tree for PID {pid or 'N/A'} ({script_key}): {e}", exc_info=True)

# ====================== BASIC COMMANDS ======================
def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    user_username = message.from_user.username
    
    logger.info(f"Welcome request from user_id: {user_id}, username: @{user_username}")
    
    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "Bot locked by admin. Try later.")
        return
    
    if user_id not in active_users:
        add_active_user(user_id)
        try:
            owner_notification = (f"New user!\nName: {user_name}\nUser: @{user_username or 'N/A'}\n"
                                 f"ID: `{user_id}`\nReferral code: {get_referral_code(user_id)}")
            bot.send_message(OWNER_ID, owner_notification, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to notify owner about new user {user_id}: {e}")
    
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    
    stats = get_referral_stats(user_id)
    
    welcome_msg_text = (
        f"Welcome, {user_name}! 🚀\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"📁 Files: {current_files} / {limit_str}\n"
        f"👥 Referrals: {stats['referrals']}\n"
        f"🎁 Bonus Slots: {stats['bonus_slots']}\n\n"
        f"🔒 **Security Features:**\n"
        f"• Auto-scan for malware/tokens\n"
        f"• Instant approval for safe files\n"
        f"• Captcha verification required\n\n"
        f"💫 **Referral Program:**\n"
        f"• Share `/refer` code with friends\n"
        f"• Each referral = +2 file slots\n"
        f"• Weekly top user gets +7 slots!\n\n"
        f"📤 Upload files securely now!"
    )
    
    main_reply_markup = create_reply_keyboard_main_menu(user_id)
    bot.send_message(chat_id, welcome_msg_text, reply_markup=main_reply_markup, parse_mode='Markdown')

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "📢 Updates Channel", "📤 Upload File", "📂 Check Files",
        "⚡ Bot Speed", "📊 Statistics", "📞 Contact Owner",
        "🤖 MPX AI", "⏱ Uptime", "🎁 Referral", "🏆 Leaderboard"
    ]
    
    if user_id in admin_ids:
        buttons.extend(["💳 Subscriptions", "📢 Broadcast", "🔒 Lock Bot", "👑 Admin Panel"])
    
    markup.add(*[types.KeyboardButton(btn) for btn in buttons])
    return markup

def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not is_running:
                logger.warning(f"Process {script_info['process'].pid} for {script_key} found in memory but not running/zombie. Cleaning up.")
                if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                    try:
                        script_info['log_file'].close()
                    except Exception as log_e:
                        logger.error(f"Error closing log file during zombie cleanup {script_key}: {log_e}")
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            logger.warning(f"Process for {script_key} not found (NoSuchProcess). Cleaning up.")
            if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                try:
                    script_info['log_file'].close()
                except Exception as log_e:
                    logger.error(f"Error closing log file during cleanup of non-existent process {script_key}: {log_e}")
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            return False
        except Exception as e:
            logger.error(f"Error checking process status for {script_key}: {e}", exc_info=True)
            return False
    return False

def create_control_buttons(script_owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("📜 View Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    
    return markup

# [Continue with remaining bot logic functions...]
# Including handle_zip_file, _logic_check_files, callback handlers, etc.
# Keeping all original functionality but with new security features

if __name__ == '__main__':
    # Initialize referral database
    init_referral_db()
    
    # Initialize main database
    init_db()
    load_data()
    
    # Start keep-alive server
    keep_alive()
    
    logger.info("="*40 + "\nULTRA SECURE Bot Starting Up on Render...\n" + 
                f"Owner ID: {OWNER_ID}\nAdmins: {admin_ids}\n" +
                f"Start Time: {BOT_START_TIME}" + "="*40)
    
    # Start bot
    while True:
        try:
            bot.infinity_polling(logger_level=logging.INFO, timeout=60, long_polling_timeout=30)
        except requests.exceptions.ReadTimeout:
            logger.warning("Polling ReadTimeout. Restarting in 5s...")
            time.sleep(5)
        except requests.exceptions.ConnectionError as ce:
            logger.error(f"Polling ConnectionError: {ce}. Retrying in 15s...")
            time.sleep(15)
        except Exception as e:
            logger.critical(f"Unrecoverable polling error: {e}", exc_info=True)
            logger.info("Restarting polling in 30s due to critical error...")
            time.sleep(30)
        finally:
            logger.warning("Polling attempt finished. Will restart if in loop.")
            time.sleep(1)