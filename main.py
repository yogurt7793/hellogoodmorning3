
"""책모아 메인 도서관: 캐릭터 이동, 독서 기록, 책갈피 PNG, 간단 계정 로그인."""
import hashlib
import hmac
import os
import re
import sqlite3
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
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 300_000
    )


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
            "SELECT id,salt,password_hash FROM users WHERE username=?",
            (username,)
        ).fetchone()
    if row and hmac.compare_digest(
        password_digest(password, row[1]), row[2]
    ):
        return row[0]
    return None


def load_records(user_id):
    with connect_db() as db:
        book_rows = db.execute(
            "SELECT book_key,title,author FROM books WHERE user_id=?",
            (user_id,)
        ).fetchall()
        review_rows = db.execute(
            "SELECT book_key,rating,content FROM reviews WHERE user_id=?",
            (user_id,)
        ).fetchall()
        report_rows = db.execute(
            "SELECT book_key,reason,scene,thought FROM reports WHERE user_id=?",
            (user_id,)
        ).fetchall()
    st.session_state.bm_books = {
        k: {"title": title, "author": author}
        for k, title, author in book_rows
    }
    st.session_state.bm_reviews = {
        k: {"rating": rating, "text": content}
        for k, rating, content in review_rows
    }
    st.session_state.bm_reports = {
        k: {"reason": a, "scene": b, "thought": c}
        for k, a, b, c in report_rows
    }
    st.session_state.bm_current = next(
        iter(st.session_state.bm_books), None
    )
    st.session_state.bm_png = None


def save_book(user_id, key, title, author):
    if user_id is None:
        return
    with connect_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO books VALUES(?,?,?,?)",
            (user_id, key, title, author),
        )


def save_review(user_id, key, rating, content):
    if user_id is None:
        return
    with connect_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO reviews VALUES(?,?,?,?)",
            (user_id, key, rating, content),
        )


def save_report(user_id, key, reason, scene, thought):
    if user_id is None:
        return
    with connect_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO reports VALUES(?,?,?,?,?)",
            (user_id, key, reason, scene, thought),
        )


def delete_record(table, user_id, key):
    if user_id is None:
        return
    if table not in ("reviews", "reports"):
        return
    with connect_db() as db:
        db.execute(
            f"DELETE FROM {table} WHERE user_id=? AND book_key=?",
            (user_id, key)
        )


# ────────── 그림 생성 ──────────
def korean_font(size):
    for p in FONT_FILES:
        if Path(p).is_file():
            return ImageFont.truetype(p, size)
    raise ValueError(
        "한글 글꼴이 없습니다. 저장소에 packages.txt를 추가해 주세요."
    )


def centered_text(draw, text, x, y, font, color):
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        (x - (box[2] - box[0]) / 2, y),
        text, font=font, fill=color
    )


def text_lines(draw, text, font, width):
    lines, part = [], ""
    for char in text:
        if char == "\n":
            lines.append(part)
            part = ""
        elif draw.textbbox(
            (0, 0), part + char, font=font
        )[2] <= width:
            part += char
        else:
            if part:
                lines.append(part)
            part = char
    if part:
        lines.append(part)
    return lines


def cute_character(draw, cx, base_y):
    """큰 얼굴, 토끼 귀, 볼터치가 있는 책 요정 캐릭터."""
    # 그림자와 발
    draw.ellipse(
        (cx - 42, base_y - 8, cx + 43, base_y + 6),
        fill="#C3B1AA"
    )
    draw.ellipse(
        (cx - 32, base_y - 25, cx - 3, base_y + 2),
        fill="#7E658C"
    )
    draw.ellipse(
        (cx + 4, base_y - 25, cx + 34, base_y + 2),
        fill="#7E658C"
    )

    # 몸과 작은 책
    draw.rounded_rectangle(
        (cx - 38, base_y - 97, cx + 38, base_y - 18),
        radius=28, fill="#A28BDD"
    )
    draw.rounded_rectangle(
        (cx - 27, base_y - 75, cx + 25, base_y - 39),
        radius=6, fill="#FFE9B4",
        outline="#8A6A58", width=2
    )
    draw.line(
        (cx, base_y - 74, cx, base_y - 40),
        fill="#D9AF82", width=2
    )
    draw.ellipse(
        (cx - 46, base_y - 77, cx - 28, base_y - 57),
        fill="#FFD4BB"
    )
    draw.ellipse(
        (cx + 28, base_y - 77, cx + 46, base_y - 57),
        fill="#FFD4BB"
    )

    # 토끼 머리띠
    draw.ellipse(
        (cx - 32, base_y - 172, cx - 7, base_y - 110),
        fill="#F5EAF7", outline="#9B86B0", width=2
    )
    draw.ellipse(
        (cx + 7, base_y - 172, cx + 32, base_y - 110),
        fill="#F5EAF7", outline="#9B86B0", width=2
    )
    draw.ellipse(
        (cx - 26, base_y - 161, cx - 13, base_y - 119),
        fill="#F3B5CC"
    )
    draw.ellipse(
        (cx + 13, base_y - 161, cx + 26, base_y - 119),
        fill="#F3B5CC"
    )

    # 머리와 얼굴
    draw.ellipse(
        (cx - 51, base_y - 147, cx + 51, base_y - 63),
        fill="#4A3A41"
    )
    draw.ellipse(
        (cx - 46, base_y - 143, cx + 46, base_y - 63),
        fill="#FFD9C3"
    )
    draw.pieslice(
        (cx - 46, base_y - 149, cx + 47, base_y - 79),
        170, 360, fill="#4A3A41"
    )

    # 눈과 반짝임
    for ex in (cx - 19, cx + 19):
        draw.ellipse(
            (ex - 6, base_y - 104, ex + 6, base_y - 89),
            fill="#27202A"
        )
        draw.ellipse(
            (ex - 2, base_y - 102, ex + 1, base_y - 99),
            fill="white"
        )

    # 볼터치와 입
    draw.ellipse(
        (cx - 39, base_y - 88, cx - 19, base_y - 76),
        fill="#F3A3AA"
    )
    draw.ellipse(
        (cx + 19, base_y - 88, cx + 39, base_y - 76),
        fill="#F3A3AA"
    )
    draw.arc(
        (cx - 8, base_y - 91, cx + 8, base_y - 81),
        10, 170, fill="#A65F63", width=2
    )


@st.cache_data(show_spinner=False)
def draw_shelf(zone, selected):
    """서로 다른 디자인의 서가를 그린다."""
    w, h = 360, 365
    walls = ["#FFF1E2", "#E7F4EE", "#F0E9F8"]
    accents = ["#B78366", "#559C91", "#8E75B4"]
    wood = ["#9C6D55", "#547E78", "#7C6796"]
    colors = [
        "#DDA88B", "#7DADD1", "#E4C57E",
        "#B39AD5", "#8CC3AD"
    ]

    img = Image.new("RGB", (w, h), walls[zone])
    d = ImageDraw.Draw(img)
    d.rectangle((0, 291, w, h), fill="#E4D8CB")
    d.line((0, 292, w, 292), fill="#BCA99C", width=4)

    # 공간마다 다른 책장 디자인
    if zone == 0:
        d.rounded_rectangle(
            (32, 40, 329, 290), radius=23,
            fill=wood[zone], outline="#6B4B3B", width=5
        )
        d.rounded_rectangle(
            (49, 64, 311, 277), radius=10,
            fill="#F9E7C9"
        )
    elif zone == 1:
        d.rounded_rectangle(
            (24, 50, 336, 291), radius=55,
            fill=wood[zone], outline="#2D685F", width=5
        )
        d.rounded_rectangle(
            (45, 72, 316, 275), radius=38,
            fill="#D7F0E7"
        )
    else:
        d.rounded_rectangle(
            (32, 50, 328, 291), radius=8,
            fill=wood[zone], outline="#594578", width=5
        )
        d.polygon(
            [(32, 50), (60, 20), (300, 20), (328, 50)],
            fill="#AB95C7"
        )
        d.rectangle(
            (48, 69, 312, 275), fill="#F7EDFB"
        )

    for row, y in enumerate((95, 164, 232)):
        for j in range(10):
            x = 58 + j * 25
            height = 31 + (j * 3 + row * 7) % 15
            tilt = (j + row) % 3
            col = colors[
                (zone + j + row) % len(colors)
            ]
            d.rounded_rectangle(
                (x, y + 42 - height, x + 17 - tilt, y + 42),
                radius=2, fill=col,
                outline="#887A74", width=1
            )
            d.line(
                (x + 4, y + 39 - height, x + 4, y + 34 - height),
                fill="#FFF6E8", width=2
            )

        d.rounded_rectangle(
            (45, y + 42, 314, y + 51),
            radius=2, fill=accents[zone]
        )

    # 책장별 장식
    if zone == 0:
        d.ellipse(
            (23, 254, 53, 283), fill="#8EA883"
        )
        d.rectangle(
            (31, 273, 48, 293), fill="#BB8B66"
        )
    elif zone == 1:
        d.ellipse(
            (18, 257, 48, 286), fill="#82BB9A"
        )
        d.ellipse(
            (310, 246, 342, 280), fill="#9FD0AB"
        )
        d.rectangle(
            (20, 275, 46, 293), fill="#CF9B7B"
        )
    else:
        d.ellipse(
            (17, 250, 49, 282), fill="#D6ABC7"
        )
        d.ellipse(
            (312, 248, 344, 281), fill="#D6ABC7"
        )
        d.ellipse(
            (161, 25, 200, 60), fill="#F0C96C"
        )

    if selected:
        d.rounded_rectangle(
            (5, 5, 355, 359),
            radius=22, outline="#F0BC49", width=8
        )
        cute_character(d, 184, 350)
    else:
        d.ellipse(
            (165, 315, 195, 345), fill="#E2D9D1"
        )
        d.ellipse(
            (171, 320, 189, 338), fill=accents[zone]
        )

    return img


def create_bookmark(title, author, quote, theme):
    bg, accent, ink = THEMES[theme]

    img = Image.new("RGB", (540, 900), bg)
    d = ImageDraw.Draw(img)

    d.rounded_rectangle(
        (22, 22, 518, 878),
        radius=23, outline=accent, width=5
    )
    d.line(
        (74, 142, 466, 142),
        fill=accent, width=3
    )

    centered_text(
        d, "MY BOOKMARK", 270, 75,
        korean_font(28), accent
    )

    title_lines = text_lines(
        d, title, korean_font(36), 425
    )
    if len(title_lines) > 3:
        raise ValueError("책 제목이 너무 깁니다.")

    for n, line in enumerate(title_lines):
        centered_text(
            d, line, 270, 180 + n * 53,
            korean_font(36), ink
        )

    if author:
        author_lines = text_lines(
            d, author, korean_font(21), 415
        )
        for n, line in enumerate(author_lines[:2]):
            centered_text(
                d, line, 270, 355 + n * 30,
                korean_font(21), accent
            )

    quote_lines = text_lines(
        d, quote, korean_font(29), 400
    )
    if len(quote_lines) > 7:
        raise ValueError(
            "책갈피 문장이 너무 깁니다. 조금 줄여 주세요."
        )

    start_y = 515 - len(quote_lines) * 25
    for n, line in enumerate(quote_lines):
        centered_text(
            d, line, 270, start_y + n * 52,
            korean_font(29), ink
        )

    d.line(
        (74, 796, 466, 796),
        fill=accent, width=3
    )
    centered_text(
        d, "책모아 도서관", 270, 824,
        korean_font(24), accent
    )

    output = BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


# ────────── 초기 상태 / 사이드바 ──────────
def initialize_state():
    defaults = {
        "bm_position": 0,
        "bm_active": None,
        "bm_books": {},
        "bm_reviews": {},
        "bm_reports": {},
        "bm_current": None,
        "bm_png": None,
        "bm_user_id": None,
        "bm_username": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def book_key(title, author):
    return (
        title.strip().casefold()
        + "|"
        + author.strip().casefold()
    )


init_db()
initialize_state()

with st.sidebar:
    st.title("📚 책모아")
    st.markdown("#### 페이지 이동")

    # 실제 존재하는 페이지 파일을 찾아 연결
    st.page_link(
        "main.py",
        label="🏠 MAIN · 도서관"
    )

    page_dir = ROOT / "pages"
    page_files = (
        sorted(page_dir.glob("*.py"))
        if page_dir.exists()
        else []
    )

    shortform_page = next(
        (
            p for p in page_files
            if "숏폼" in p.name
            or "shortform" in p.name.lower()
        ),
        None,
    )

    if shortform_page:
        st.page_link(
            f"pages/{shortform_page.name}",
            label="🎮 PAGE 1 · 숏폼 브레이커"
        )
    else:
        st.warning(
            "PAGE 1 파일을 pages 폴더에서 찾지 못했습니다."
        )

    escape_page = next(
        (
            p for p in page_files
            if "탈출" in p.name
            or "escape" in p.name.lower()
        ),
        None,
    )

    if escape_page:
        st.page_link(
            f"pages/{escape_page.name}",
            label="🗝️ PAGE 2 · 책 속 탈출"
        )

    st.divider()
    st.markdown("#### 👤 내 기록")

    if st.session_state.bm_user_id is not None:
        st.success(
            f"{st.session_state.bm_username}님 로그인 중"
        )

        if st.button(
            "로그아웃",
            use_container_width=True
        ):
            st.session_state.bm_user_id = None
            st.session_state.bm_username = None
            st.session_state.bm_books = {}
            st.session_state.bm_reviews = {}
            st.session_state.bm_reports = {}
            st.session_state.bm_current = None
            st.session_state.bm_png = None
            st.rerun()

    else:
        login_tab, signup_tab = st.tabs(
            ["로그인", "회원가입"]
        )

        with login_tab:
            with st.form("bm_login_form"):
                login_name = st.text_input("아이디")
                login_pw = st.text_input(
                    "비밀번호",
                    type="password"
                )
                login_submit = st.form_submit_button(
                    "로그인",
                    use_container_width=True
                )

            if login_submit:
                user_id = authenticate(
                    login_name.strip(), login_pw
                )
                if user_id is None:
                    st.error(
                        "아이디 또는 비밀번호를 확인해 주세요."
                    )
                else:
                    st.session_state.bm_user_id = user_id
                    st.session_state.bm_username = (
                        login_name.strip()
                    )
                    load_records(user_id)
                    st.rerun()

        with signup_tab:
            with st.form("bm_signup_form"):
                new_name = st.text_input(
                    "새 아이디 (영문·숫자·_)"
                )
                new_pw = st.text_input(
                    "새 비밀번호 (8자 이상)",
                    type="password"
                )
                new_pw_confirm = st.text_input(
                    "비밀번호 확인",
                    type="password"
                )
                signup_submit = st.form_submit_button(
                    "회원가입",
                    use_container_width=True
                )

            if signup_submit:
                if new_pw != new_pw_confirm:
                    st.error(
                        "비밀번호가 일치하지 않습니다."
                    )
                else:
                    message = register_user(
                        new_name.strip(), new_pw
                    )
                    if message:
                        st.error(message)
                    else:
                        st.success(
                            "가입 완료! 로그인 탭에서 로그인해 주세요."
                        )

        st.caption(
            "로그인하지 않아도 체험할 수 있지만 "
            "기록은 현재 접속 중에만 유지됩니다."
        )

    st.caption(
        "학습용 로컬 DB입니다. 클라우드 서버가 "
        "재시작되면 계정과 기록이 사라질 수 있습니다."
    )


# ────────── 메인 화면 ──────────
st.title("📖 책모아 도서관")

st.caption(
    "책장 사이를 이동하며 책에 대한 생각을 기록하고 "
    "나만의 책갈피를 만들어 보세요."
)

st.markdown("### 🏛️ 도서관 둘러보기")

columns = st.columns(3, gap="small")

for index, col in enumerate(columns):
    with col:
        # 한글 제목은 Streamlit 글자로 출력
        st.markdown(
            f"#### {ICONS[index]} {ZONES[index]} 공간"
        )
        st.image(
            draw_shelf(
                index,
                st.session_state.bm_position == index
            ),
            use_container_width=True
        )

left, center, right = st.columns([1, 2, 1])

with left:
    if st.button(
        "◀ 왼쪽 이동",
        disabled=st.session_state.bm_position == 0,
        use_container_width=True
    ):
        st.session_state.bm_position -= 1
        st.session_state.bm_active = None
        st.rerun()

with center:
    current_zone = ZONES[
        st.session_state.bm_position
    ]

    if st.button(
        f"🚪 {current_zone} 공간 입장",
        type="primary",
        use_container_width=True
    ):
        st.session_state.bm_active = (
            st.session_state.bm_position
        )
        st.rerun()

with right:
    if st.button(
        "오른쪽 이동 ▶",
        disabled=st.session_state.bm_position == 2,
        use_container_width=True
    ):
        st.session_state.bm_position += 1
        st.session_state.bm_active = None
        st.rerun()


# ────────── 책 선택 ──────────
st.divider()
st.subheader("📘 활동할 책 선택")

with st.form(
    "bm_book_form",
    clear_on_submit=True
):
    col_title, col_author = st.columns(2)

    title = col_title.text_input(
        "책 제목 *",
        max_chars=100
    )
    author = col_author.text_input(
        "저자 (선택)",
        max_chars=70
    )

    submitted_book = st.form_submit_button(
        "이 책으로 활동하기"
    )

if submitted_book:
    if not title.strip():
        st.warning("책 제목을 입력해 주세요.")
    else:
        key = book_key(title, author)

        book = {
            "title": title.strip(),
            "author": author.strip()
        }

        st.session_state.bm_books[key] = book
        st.session_state.bm_current = key
        st.session_state.bm_png = None

        save_book(
            st.session_state.bm_user_id,
            key,
            book["title"],
            book["author"]
        )
        st.rerun()

if st.session_state.bm_books:
    book_ids = list(st.session_state.bm_books)

    selected = st.selectbox(
        "등록한 책 목록",
        book_ids,
        index=(
            book_ids.index(
                st.session_state.bm_current
            )
            if st.session_state.bm_current in book_ids
            else 0
        ),
        format_func=lambda key: (
            st.session_state.bm_books[key]["title"]
        ),
    )

    if selected != st.session_state.bm_current:
        if st.button(
            "이 책 선택",
            use_container_width=True
        ):
            st.session_state.bm_current = selected
            st.session_state.bm_png = None
            st.rerun()
else:
    st.info(
        "책 제목을 입력하면 한줄평·독후감·책갈피를 "
        "만들 수 있습니다."
    )

book_id = st.session_state.bm_current
book = (
    st.session_state.bm_books.get(book_id)
    if book_id else None
)
active = st.session_state.bm_active
user_id = st.session_state.bm_user_id


# ────────── 공간별 기능 ──────────
if active is None:
    st.info(
        "캐릭터를 움직이고 '공간 입장'을 누르면 "
        "해당 활동이 열립니다."
    )

elif book is None:
    st.info("먼저 활동할 책을 등록해 주세요.")

else:
    st.divider()
    st.subheader(
        f"{ICONS[active]} "
        f"{ZONES[active]} · {book['title']}"
    )

    # 1. 한줄평 작성
    if active == 0:
        saved = st.session_state.bm_reviews.get(
            book_id, {}
        )

        with st.form(f"bm_review_{book_id}"):
            rating = st.slider(
                "별점",
                1, 5,
                value=saved.get("rating", 3)
            )

            content = st.text_area(
                "한줄평 (10~100자)",
                value=saved.get("text", ""),
                max_chars=100
            )

            save_clicked = st.form_submit_button(
                "한줄평 저장",
                type="primary"
            )

        if save_clicked:
            if len(content.strip()) < 10:
                st.warning(
                    "한줄평은 10자 이상 작성해 주세요."
                )
            else:
                st.session_state.bm_reviews[book_id] = {
                    "rating": rating,
                    "text": content.strip()
                }

                save_review(
                    user_id,
                    book_id,
                    rating,
                    content.strip()
                )
                st.rerun()

        if saved:
            st.success(
                "⭐" * saved["rating"]
                + " "
                + saved["text"]
            )

            if st.button("한줄평 삭제"):
                st.session_state.bm_reviews.pop(
                    book_id, None
                )
                delete_record(
                    "reviews", user_id, book_id
                )
                st.rerun()

    # 2. 독후감 작성
    elif active == 1:
        saved = st.session_state.bm_reports.get(
            book_id, {}
        )

        with st.form(f"bm_report_{book_id}"):
            reason = st.text_area(
                "1. 읽게 된 이유",
                value=saved.get("reason", ""),
                height=100
            )

            scene = st.text_area(
                "2. 인상 깊었던 내용",
                value=saved.get("scene", ""),
                height=115
            )

            thought = st.text_area(
                "3. 읽고 난 뒤의 생각",
                value=saved.get("thought", ""),
                height=115
            )

            save_clicked = st.form_submit_button(
                "독후감 저장",
                type="primary"
            )

        if save_clicked:
            if not all(
                part.strip()
                for part in (reason, scene, thought)
            ):
                st.warning(
                    "세 항목을 모두 작성해 주세요."
                )
            else:
                clean = {
                    "reason": reason.strip(),
                    "scene": scene.strip(),
                    "thought": thought.strip()
                }

                st.session_state.bm_reports[
                    book_id
                ] = clean

                save_report(
                    user_id, book_id, **clean
                )
                st.rerun()

        if saved:
            full_text = (
                f"[{book['title']}] 독후감\n\n"
                f"1. 읽게 된 이유\n"
                f"{saved['reason']}\n\n"
                f"2. 인상 깊었던 내용\n"
                f"{saved['scene']}\n\n"
                f"3. 읽고 난 뒤의 생각\n"
                f"{saved['thought']}"
            )

            st.text_area(
                "저장된 독후감",
                value=full_text,
                height=250,
                disabled=True
            )

            st.download_button(
                "📥 독후감 TXT 다운로드",
                full_text.encode("utf-8-sig"),
                file_name="bookmoa_report.txt",
                mime="text/plain"
            )

            if st.button("독후감 삭제"):
                st.session_state.bm_reports.pop(
                    book_id, None
                )
                delete_record(
                    "reports", user_id, book_id
                )
                st.rerun()

    # 3. 책갈피 생성
    elif active == 2:
        review_text = (
            st.session_state.bm_reviews
            .get(book_id, {})
            .get("text", "")
        )

        quote = st.text_area(
            "책갈피에 넣을 문장",
            value=review_text,
            max_chars=100,
            key=f"bm_quote_{book_id}"
        )

        theme = st.selectbox(
            "디자인",
            list(THEMES),
            key="bm_theme"
        )

        if st.button(
            "책갈피 PNG 만들기",
            type="primary"
        ):
            if not quote.strip():
                st.warning(
                    "책갈피에 넣을 문장을 작성해 주세요."
                )
            else:
                try:
                    st.session_state.bm_png = (
                        create_bookmark(
                            book["title"],
                            book["author"],
                            quote.strip(),
                            theme
                        )
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

        if st.session_state.bm_png:
            st.image(
                st.session_state.bm_png,
                width=280
            )

            st.download_button(
                "📥 책갈피 PNG 다운로드",
                st.session_state.bm_png,
                file_name="bookmoa_bookmark.png",
                mime="image/png"
            )


# ────────── 독서 기록 조회 ──────────
st.divider()

with st.expander("📒 내 독서 기록 보기"):
    if not st.session_state.bm_books:
        st.write("아직 등록한 책이 없습니다.")
    else:
        for key, entry in (
            st.session_state.bm_books.items()
        ):
            st.markdown(
                f"**📖 {entry['title']}**"
            )

            if key in st.session_state.bm_reviews:
                item = (
                    st.session_state
                    .bm_reviews[key]
                )

                st.write(
                    "⭐" * item["rating"],
                    item["text"]
                )

            if key in st.session_state.bm_reports:
                st.write("📝 독후감 저장 완료")

    if user_id is None:
        st.caption(
            "로그인하지 않은 기록은 브라우저 "
            "세션 종료 후 유지되지 않습니다."
        )
    else:
        st.caption(
            "로그인한 계정의 기록입니다. "
            "현재 서버의 로컬 DB에 저장됩니다."
        )
