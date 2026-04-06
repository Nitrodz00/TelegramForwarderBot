import os
import sqlite3
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# في حالة وجود PostgreSQL نستخدم مكتبة psycopg2، وإلا نستخدم sqlite3 المحلي
if DATABASE_URL:
    import psycopg2
    from psycopg2.extras import DictCursor
    USE_POSTGRES = True
    # بعض المنصات مثل Railway تعطي postgres:// بدلاً من postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    USE_POSTGRES = False
    DB_NAME = "bot_data.db"

def get_connection():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(DB_NAME)
        return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        auto_inc = "SERIAL PRIMARY KEY"
        ignore = "ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value"
        ignore_channels = "ON CONFLICT (user_id, channel_id) DO UPDATE SET title = EXCLUDED.title, channel_type = EXCLUDED.channel_type"
    else:
        auto_inc = "INTEGER PRIMARY KEY AUTOINCREMENT"
        ignore = ""
        ignore_channels = ""

    # جدول الإعدادات
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS settings (
            user_id BIGINT,
            key TEXT,
            value TEXT,
            PRIMARY KEY (user_id, key)
        )
    ''')
    
    # جدول القنوات
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS channels (
            user_id BIGINT,
            channel_id TEXT,
            channel_type TEXT,
            title TEXT,
            PRIMARY KEY (user_id, channel_id)
        )
    ''')
    
    # جدول خرائط الرسائل (للتعديل التلقائي)
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS message_map (
            id {auto_inc},
            user_id BIGINT,
            source_chat_id TEXT,
            source_message_id BIGINT,
            dest_chat_id TEXT,
            dest_message_id BIGINT
        )
    ''')
    
    conn.commit()
    conn.close()

# ========== مساعد المتغيرات (للتعامل مع ? و %s) ==========
def q(query):
    if USE_POSTGRES:
        return query.replace("?", "%s")
    return query

# ========== إعدادات المستخدم ==========

def is_bot_active(user_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(q('SELECT value FROM settings WHERE user_id=? AND key=\'is_active\''), (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] == "1" if res else True

def set_bot_active(user_id: int, state: bool):
    conn = get_connection()
    cursor = conn.cursor()
    val = "1" if state else "0"
    if USE_POSTGRES:
        cursor.execute(
            'INSERT INTO settings (user_id, key, value) VALUES (%s, \'is_active\', %s) ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value',
            (user_id, val)
        )
    else:
        cursor.execute(
            'INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, "is_active", ?)',
            (user_id, val)
        )
    conn.commit()
    conn.close()

# ========== إدارة القنوات ==========

def add_channel(user_id: int, channel_id: str, title: str, c_type: str):
    conn = get_connection()
    cursor = conn.cursor()
    if USE_POSTGRES:
        cursor.execute(
            'INSERT INTO channels (user_id, channel_id, channel_type, title) VALUES (%s, %s, %s, %s) ON CONFLICT (user_id, channel_id) DO UPDATE SET title = EXCLUDED.title, channel_type = EXCLUDED.channel_type',
            (user_id, str(channel_id), c_type, title)
        )
    else:
        cursor.execute(
            'INSERT OR REPLACE INTO channels (user_id, channel_id, channel_type, title) VALUES (?, ?, ?, ?)',
            (user_id, str(channel_id), c_type, title)
        )
    conn.commit()
    conn.close()

def remove_channel(user_id: int, channel_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(q('DELETE FROM channels WHERE user_id=? AND channel_id=?'), (user_id, str(channel_id)))
    conn.commit()
    conn.close()

def get_channels(user_id: int, c_type: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    if c_type:
        cursor.execute(
            q('SELECT channel_id, title FROM channels WHERE user_id=? AND channel_type=?'),
            (user_id, c_type)
        )
    else:
        cursor.execute(
            q('SELECT channel_id, title, channel_type FROM channels WHERE user_id=?'),
            (user_id,)
        )
    res = cursor.fetchall()
    conn.close()
    return res

def get_all_sources_with_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(q('SELECT user_id, channel_id FROM channels WHERE channel_type=\'source\''))
    res = cursor.fetchall()
    conn.close()
    return res

# ========== ربط الرسائل للتعديل ==========

def save_message_mapping(user_id: int, src_chat: str, src_msg: int, dst_chat: str, dst_msg: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        q('INSERT INTO message_map (user_id, source_chat_id, source_message_id, dest_chat_id, dest_message_id) VALUES (?, ?, ?, ?, ?)'),
        (user_id, str(src_chat), src_msg, str(dst_chat), dst_msg)
    )
    conn.commit()
    conn.close()

def get_mapped_messages(src_chat: str, src_msg: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        q('SELECT user_id, dest_chat_id, dest_message_id FROM message_map WHERE source_chat_id=? AND source_message_id=?'),
        (str(src_chat), src_msg)
    )
    res = cursor.fetchall()
    conn.close()
    return res

def get_dest_msg_id(user_id: int, src_chat: str, src_msg: int, dst_chat: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        q('SELECT dest_message_id FROM message_map WHERE user_id=? AND source_chat_id=? AND source_message_id=? AND dest_chat_id=?'),
        (user_id, str(src_chat), src_msg, str(dst_chat))
    )
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None
