"""책모아 메인 도서관: 캐릭터 이동, 독서 기록, 책갈피 PNG, 간단 계정 로그인."""
import hashlib
import hmac
import os
import re
import sqlite3
import unicodedata
from io import BytesIO
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(
    page_title="책모아 도서관", page_icon="📚", layout="wide",
    initial_sidebar_state="expanded",
)

ROOT = Path(__file__).resolve().parent
DB_FILE = ROOT / ".bookmoa" / "records.db"
ZONES = ["한줄평", "독후감", "책갈피"]
ICONS = ["✍️", "📝", "🔖"]
THEMES = {
    "크림": ("#FAEED8", "#976A51", "#49362B"),
    "민트": ("#E4F5ED", "#467F72", "#264A40"),
    "라벤더": ("#EEE9F9", "#7F67A8", "#423653"),
}
FONT_FILES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "C:/Windows/Fonts/malgun.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]


# ────────── 데이터베이스 / 로그인 ──────────
def connect_db():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(DB_FILE), timeout=10)


def init_db():
    with connect_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            salt BLOB NOT NULL, password_hash BLOB NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS books (
            user_id INTEGER NOT NULL, book_key TEXT NOT NULL,
            title TEXT NOT NULL, author TEXT NOT NULL,
            PRIMARY KEY(user_id, book_key)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS reviews (
            user_id INTEGER NOT NULL, book_key TEXT NOT NULL,
            rating INTEGER NOT NULL, content TEXT NOT NULL,
            PRIMARY KEY(user_id, book_key)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS reports (
            user_id INTEGER NOT NULL, book_key TEXT NOT NULL,
            reason TEXT NOT NULL, scene TEXT NOT NULL, thought TEXT NOT NULL,
            PRIMARY KEY(user_id, book_key)
        )""")


def password_digest(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 300_000)


def register_user(username, password):
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", username):
        return "아이디는 영문·숫자·_를 사용해 3~20자로 입력하세요."
    if len(password) < 8:
        return "비밀번호는 8자 이상 입력하세요."
    salt = os.urandom(16)
    try:
        with connect_db() as db:
            db.execute(
                "INSERT INTO users(username,salt,password_hash) VALUES(?,?,?)",
                (username, salt, password_digest(password, salt)),
            )
    except sqlite3.IntegrityError:
        return "이미 사용 중인 아이디입니다."
    return None


def authenticate(username, password):
    with connect_db() as db:
        row = db.execute(
            "SELECT id,salt,password_hash FROM users WHERE username=?", (username,)
        ).fetchone()
    if row and hmac.compare_digest(password_digest(password, row[1]), row[2]):
        return row[0]
    return None

