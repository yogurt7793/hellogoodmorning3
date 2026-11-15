
"""책모아 MAIN 도서관.

Streamlit 멀티페이지: 같은 폴더의 pages/ 안에 PAGE 1 파이썬 파일을 둡니다.
메인 기능: 귀여운 캐릭터 이동, 한줄평, 독후감, 책갈피 PNG, 학습용 로그인.
"""

import hashlib
import hmac
import os
import re
import sqlite3
import tempfile
import unicodedata
from io import BytesIO
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(
    page_title="책모아 도서관",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE = Path(__file__).resolve().parent
DB_PATH = Path(tempfile.gettempdir()) / "bookmoa_study" / "records.sqlite3"

ZONES = ["한줄평", "독후감", "책갈피"]
ZONE_ICONS = ["💬", "📝", "🔖"]

PALETTES = {
    "크림": ("#FFF4DC", "#875D43", "#47382E"),
    "민트": ("#E4F5EB", "#367E72", "#28463D"),
    "라벤더": ("#F0E9FC", "#78629C", "#4C3B63"),
}


# -----------------------------------
# 1. 세션 상태
# -----------------------------------

def init_state():
    values = {
        "bm_position": 0,
        "bm_zone": None,
        "bm_user": None,
        "bm_username": None,
        "bm_books": {},
        "bm_book": None,
        "bm_reviews": {},
        "bm_reports": {},
        "bm_bookmark": None,
        "bm_bookmark_key": None,
    }

    for name, value in values.items():
        if name not in st.session_state:
            st.session_state[name] = value


def book_key(title, author):
    return (
        title.strip().casefold()
        + "|"
        + author.strip().casefold()
    )


# -----------------------------------
# 2. 로그인 및 기록 데이터베이스
# -----------------------------------

def db_connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH, timeout=8)


def setup_database():
    try:
        with db_connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    salt BLOB NOT NULL,
                    pw_hash BLOB NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    user_id INTEGER,
                    book_id TEXT,
                    title TEXT,
                    author TEXT,
                    PRIMARY KEY(user_id, book_id)
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    user_id INTEGER,
                    book_id TEXT,
                    rating INTEGER,
                    content TEXT,
                    PRIMARY KEY(user_id, book_id)
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    user_id INTEGER,
                    book_id TEXT,
                    reason TEXT,
                    scene TEXT,
                    thought TEXT,
                    PRIMARY KEY(user_id, book_id)
                )
            """)

        return True

    except (OSError, sqlite3.Error) as exc:
        st.warning(
            f"계정 저장소를 사용할 수 없어 "
            f"체험 모드로 실행합니다: {exc}"
        )
        return False


def pw_hash(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        150_000,
    )


def signup(username, password):
    if not re.fullmatch(
        r"[a-zA-Z0-9_]{3,20}",
        username,
    ):
        return (
            "아이디는 영문·숫자·밑줄로 "
            "3~20자 입력해 주세요."
        )

    if len(password) < 8:
        return "비밀번호는 8자 이상 입력해 주세요."

    salt = os.urandom(16)

    try:
        with db_connect() as db:
            db.execute(
                """
                INSERT INTO users(
                    username, salt, pw_hash
                )
                VALUES(?,?,?)
                """,
                (
                    username,
                    salt,
                    pw_hash(password, salt),
                ),
            )

    except sqlite3.IntegrityError:
        return "이미 사용 중인 아이디입니다."

    except (OSError, sqlite3.Error):
        return "회원가입 중 저장소 오류가 발생했습니다."

    return None


def login(username, password):
    try:
        with db_connect() as db:
            row = db.execute(
                """
                SELECT id, salt, pw_hash
                FROM users
                WHERE username=?
                """,
                (username,),
            ).fetchone()

        if row and hmac.compare_digest(
            pw_hash(password, row[1]),
            row[2],
        ):
            return row[0]

    except (OSError, sqlite3.Error):
        pass

    return None


def write_db(sql, params):
    if st.session_state.bm_user is None:
        return True

    try:
        with db_connect() as db:
            db.execute(sql, params)

        return True

    except (OSError, sqlite3.Error) as exc:
        st.error(f"저장에 실패했습니다: {exc}")
        return False


def load_account(user_id):
    try:
        with db_connect() as db:
            books = db.execute(
                """
                SELECT book_id, title, author
                FROM books
                WHERE user_id=?
                """,
                (user_id,),
            ).fetchall()

            reviews = db.execute(
                """
                SELECT book_id, rating, content
                FROM reviews
                WHERE user_id=?
                """,
                (user_id,),
            ).fetchall()

            reports = db.execute(
                """
                SELECT book_id, reason, scene, thought
                FROM reports
                WHERE user_id=?
                """,
                (user_id,),
            ).fetchall()

        st.session_state.bm_books = {
            k: {
                "title": title,
                "author": author,
            }
            for k, title, author in books
        }

        st.session_state.bm_reviews = {
            k: {
                "rating": rating,
                "text": text,
            }
            for k, rating, text in reviews
        }

        st.session_state.bm_reports = {
            k: {
                "reason": a,
                "scene": b,
                "thought": c,
            }
            for k, a, b, c in reports
        }

        st.session_state.bm_book = next(
            iter(st.session_state.bm_books),
            None,
        )

        st.session_state.bm_bookmark = None
        st.session_state.bm_bookmark_key = None

        return True

    except (OSError, sqlite3.Error) as exc:
        st.error(
            f"독서 기록을 불러오지 못했습니다: {exc}"
        )
        return False


# -----------------------------------
# 3. 도서관 책장과 캐릭터
# -----------------------------------

@st.cache_data(show_spinner=False)
def make_shelf(index, occupied):
    colors = [
        "#FFF0E1",
        "#E5F3ED",
        "#F3EDFB",
    ]

    img = Image.new(
        "RGB",
        (420, 390),
        colors[index],
    )

    d = ImageDraw.Draw(img)

    trim = [
        "#9D7357",
        "#5D9284",
        "#806AA7",
    ][index]

    inside = [
        "#F7DFC1",
        "#CDE7DB",
        "#DED3F3",
    ][index]

    d.rectangle(
        (0, 300, 420, 390),
        fill="#E0C9AD",
    )

    # 책장별로 다른 디자인

    if index == 0:
        # 전통적인 나무 책장
        d.rounded_rectangle(
            (32, 45, 390, 300),
            radius=14,
            fill=trim,
        )

        d.rounded_rectangle(
            (48, 65, 374, 285),
            radius=7,
            fill=inside,
        )

    elif index == 1:
        # 아치형 책장
        d.rounded_rectangle(
            (32, 35, 390, 300),
            radius=70,
            fill=trim,
        )

        d.rounded_rectangle(
            (49, 52, 373, 285),
            radius=58,
            fill=inside,
        )

    else:
        # 지붕 장식 책장
        d.polygon(
            [
                (30, 65),
                (95, 22),
                (326, 22),
                (390, 65),
            ],
            fill="#A993C8",
        )

        d.rounded_rectangle(
            (32, 63, 390, 300),
            radius=6,
            fill=trim,
        )

        d.rectangle(
            (49, 80, 373, 285),
            fill=inside,
        )

    book_colors = [
        "#DCA17F",
        "#79ACBF",
        "#D1BA6B",
        "#9C8AC7",
        "#76AF91",
    ]

    # 책 그리기
    for level, y in enumerate(
        (113, 183, 252)
    ):
        for j in range(12):
            x = 56 + j * 26
            size = 26 + (
                j * 3 + level * 7
            ) % 15

            d.rounded_rectangle(
                (
                    x,
                    y - size,
                    x + 18,
                    y,
                ),
                radius=2,
                fill=book_colors[
                    (index + j + level) % 5
                ],
            )

        d.rectangle(
            (48, y, 374, y + 11),
            fill=trim,
        )

    # 선택한 책장 앞에 캐릭터 표시
    if occupied:
        cx, cy = 210, 361

        # 그림자
        d.ellipse(
            (
                cx - 50,
                cy - 6,
                cx + 50,
                cy + 8,
            ),
            fill="#C7B8A9",
        )

        # 발
        d.ellipse(
            (
                cx - 34,
                cy - 40,
                cx - 4,
                cy + 3,
            ),
            fill="#756285",
        )

        d.ellipse(
            (
                cx + 4,
                cy - 40,
                cx + 34,
                cy + 3,
            ),
            fill="#756285",
        )

        # 몸통
        d.rounded_rectangle(
            (
                cx - 44,
                cy - 112,
                cx + 44,
                cy - 33,
            ),
            radius=26,
            fill="#A995E4",
        )

        # 손에 든 책
        d.rounded_rectangle(
            (
                cx - 30,
                cy - 94,
                cx + 30,
                cy - 56,
            ),
            radius=7,
            fill="#FFF0BE",
        )

        d.line(
            (
                cx,
                cy - 91,
                cx,
                cy - 57,
            ),
            fill="#D4AE86",
            width=3,
        )

        # 토끼 귀
        d.ellipse(
            (
                cx - 32,
                cy - 207,
                cx - 7,
                cy - 133,
            ),
            fill="#FFF6F8",
        )

        d.ellipse(
            (
                cx + 7,
                cy - 207,
                cx + 32,
                cy - 133,
            ),
            fill="#FFF6F8",
        )

        d.ellipse(
            (
                cx - 26,
                cy - 195,
                cx - 13,
                cy - 143,
            ),
            fill="#F3B3CE",
        )

        d.ellipse(
            (
                cx + 13,
                cy - 195,
                cx + 26,
                cy - 143,
            ),
            fill="#F3B3CE",
        )

        # 얼굴과 머리카락
        d.ellipse(
            (
                cx - 59,
                cy - 157,
                cx + 59,
                cy - 53,
            ),
            fill="#51414B",
        )

        d.ellipse(
            (
                cx - 53,
                cy - 153,
                cx + 53,
                cy - 57,
            ),
            fill="#FFDEC9",
        )

        d.pieslice(
            (
                cx - 55,
                cy - 162,
                cx + 55,
                cy - 87,
            ),
            170,
            360,
            fill="#51414B",
        )

        # 눈
        for xx in (
            cx - 22,
            cx + 22,
        ):
            d.ellipse(
                (
                    xx - 6,
                    cy - 110,
                    xx + 6,
                    cy - 93,
                ),
                fill="#2C2431",
            )

            d.ellipse(
                (
                    xx - 3,
                    cy - 107,
                    xx,
                    cy - 103,
                ),
                fill="#FFFFFF",
            )

        # 볼터치
        d.ellipse(
            (
                cx - 47,
                cy - 92,
                cx - 25,
                cy - 79,
            ),
            fill="#F2A6B4",
        )

        d.ellipse(
            (
                cx + 25,
                cy - 92,
                cx + 47,
                cy - 79,
            ),
            fill="#F2A6B4",
        )

        # 웃는 입
        d.arc(
            (
                cx - 10,
                cy - 94,
                cx + 10,
                cy - 82,
            ),
            0,
            180,
            fill="#B76C7A",
            width=3,
        )

        # 현재 선택 책장 강조
        d.rounded_rectangle(
            (5, 5, 415, 385),
            radius=22,
            outline="#F2C34E",
            width=8,
        )

    return img


# -----------------------------------
# 4. 한글 글꼴과 책갈피 PNG
# -----------------------------------

def korean_font(size):
    candidates = [
        BASE / "fonts" / "NanumGothic.ttf",
        Path(
            "/usr/share/fonts/opentype/noto/"
            "NotoSansCJK-Regular.ttc"
        ),
        Path(
            "/usr/share/fonts/truetype/nanum/"
            "NanumGothic.ttf"
        ),
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path(
            "/System/Library/Fonts/"
            "AppleSDGothicNeo.ttc"
        ),
    ]

    for path in candidates:
        if path.exists():
            return ImageFont.truetype(
                str(path),
                size,
            )

    return None


def wrap_line(draw, text, font, width):
    lines = []
    line = ""

    for ch in text:
        if ch == "\n":
            lines.append(line)
            line = ""

        elif draw.textbbox(
            (0, 0),
            line + ch,
            font=font,
        )[2] <= width:
            line += ch

        else:
            lines.append(line)
            line = ch

    if line:
        lines.append(line)

    return lines


def bookmark_png(
    title,
    author,
    quote,
    palette,
):
    font = korean_font(29)

    if font is None:
        raise ValueError(
            "한글 글꼴이 없습니다. "
            "packages.txt에 fonts-noto-cjk를 "
            "추가해 주세요."
        )

    title_font = korean_font(36)
    small_font = korean_font(22)

    bg, accent, ink = PALETTES[palette]

    img = Image.new(
        "RGB",
        (560, 920),
        bg,
    )

    d = ImageDraw.Draw(img)

    d.rounded_rectangle(
        (20, 20, 540, 900),
        radius=25,
        outline=accent,
        width=5,
    )

    d.text(
        (155, 75),
        "MY BOOKMARK",
        font=small_font,
        fill=accent,
    )

    d.line(
        (65, 140, 495, 140),
        fill=accent,
        width=3,
    )

    # 책 제목
    title_lines = wrap_line(
        d,
        title,
        title_font,
        440,
    )

    for i, line in enumerate(
        title_lines[:3]
    ):
        d.text(
            (60, 184 + 51 * i),
            line,
            font=title_font,
            fill=ink,
        )

    # 저자
    author_lines = wrap_line(
        d,
        author,
        small_font,
        440,
    )

    for i, line in enumerate(
        author_lines[:2]
    ):
        d.text(
            (60, 360 + 34 * i),
            line,
            font=small_font,
            fill=accent,
        )

    # 책갈피 문장
    lines = wrap_line(
        d,
        quote,
        font,
        440,
    )

    if len(lines) > 8:
        raise ValueError(
            "책갈피 문장을 조금 줄여 주세요. "
            "(최대 8줄)"
        )

    top = 480 - 24 * len(lines)

    for i, line in enumerate(lines):
        d.text(
            (60, top + 50 * i),
            line,
            font=font,
            fill=ink,
        )

    # 하단 장식
    d.line(
        (65, 790, 495, 790),
        fill=accent,
        width=3,
    )

    d.text(
        (165, 820),
        "책모아 도서관",
        font=small_font,
        fill=accent,
    )

    out = BytesIO()
    img.save(
        out,
        format="PNG",
    )

    return out.getvalue()


# -----------------------------------
# 5. 메인 화면 시작
# -----------------------------------

init_state()

st.title("📚 책모아 도서관")

st.caption(
    "책장 사이를 이동하며 한줄평, "
    "독후감, 책갈피를 만들어 보세요."
)

db_available = setup_database()


# -----------------------------------
# 6. 사이드바
# -----------------------------------

with st.sidebar:
    st.header("📚 책모아")
    st.subheader("페이지 이동")

    try:
        st.page_link(
            "main.py",
            label="🏠 MAIN · 도서관",
        )
    except Exception:
        st.write("🏠 MAIN · 도서관")

    # pages 폴더에서 PAGE 1을 찾는다.
    pages_dir = BASE / "pages"

    if pages_dir.is_dir():
        pages = sorted(
            pages_dir.glob("*.py")
        )
    else:
        pages = []

    def normalized(name):
        return unicodedata.normalize(
            "NFC",
            name,
        ).casefold()

    page1 = next(
        (
            p for p in pages
            if (
                "숏폼" in normalized(p.stem)
                or "shortform" in normalized(p.stem)
            )
        ),
        None,
    )

    # PAGE 1 이름이 다를 때 번호로 찾기
    if page1 is None:
        page1 = next(
            (
                p for p in pages
                if re.match(
                    r"^1[_ .-]",
                    normalized(p.stem),
                )
            ),
            None,
        )

    if page1:
        try:
            st.page_link(
                f"pages/{page1.name}",
                label="🎮 PAGE 1 · 숏폼 브레이커",
            )
        except Exception:
            st.warning(
                "PAGE 1 링크를 확인해 주세요: "
                + page1.name
            )
    else:
        st.info(
            "PAGE 1 파일을 pages 폴더에 "
            "넣으면 메뉴에 표시됩니다."
        )

    # PAGE 2가 추가되면 자동 표시
    page2 = next(
        (
            p for p in pages
            if (
                "탈출" in normalized(p.stem)
                or "escape" in normalized(p.stem)
            )
        ),
        None,
    )

    if page2:
        try:
            st.page_link(
                f"pages/{page2.name}",
                label="🗝️ PAGE 2 · 책 속 탈출",
            )
        except Exception:
            pass

    st.divider()
    st.subheader("👤 내 독서 기록")

    # 로그인 상태
    if st.session_state.bm_user is not None:
        st.success(
            f"{st.session_state.bm_username}"
            "님 로그인 중"
        )

        if st.button(
            "로그아웃",
            use_container_width=True,
        ):
            for key in (
                "bm_books",
                "bm_reviews",
                "bm_reports",
            ):
                st.session_state[key] = {}

            st.session_state.bm_user = None
            st.session_state.bm_username = None
            st.session_state.bm_book = None
            st.session_state.bm_bookmark = None

            st.rerun()

    elif db_available:
        tab1, tab2 = st.tabs(
            ["로그인", "회원가입"]
        )

        # 로그인
        with tab1:
            with st.form("bm_login"):
                user = st.text_input("아이디")

                password = st.text_input(
                    "비밀번호",
                    type="password",
                )

                do_login = (
                    st.form_submit_button("로그인")
                )

            if do_login:
                account_id = login(
                    user.strip(),
                    password,
                )

                if account_id is None:
                    st.error(
                        "아이디 또는 비밀번호를 "
                        "확인해 주세요."
                    )

                elif load_account(account_id):
                    st.session_state.bm_user = (
                        account_id
                    )
                    st.session_state.bm_username = (
                        user.strip()
                    )
                    st.rerun()

        # 회원가입
        with tab2:
            with st.form("bm_signup"):
                new_user = st.text_input(
                    "새 아이디"
                )

                new_pw = st.text_input(
                    "새 비밀번호 (8자 이상)",
                    type="password",
                )

                confirm = st.text_input(
                    "비밀번호 확인",
                    type="password",
                )

                do_signup = (
                    st.form_submit_button(
                        "회원가입"
                    )
                )

            if do_signup:
                if new_pw != confirm:
                    st.error(
                        "비밀번호가 일치하지 않습니다."
                    )

                else:
                    error = signup(
                        new_user.strip(),
                        new_pw,
                    )

                    if error:
                        st.error(error)

                    else:
                        st.success(
                            "가입되었습니다. "
                            "로그인 탭에서 로그인해 주세요."
                        )

    else:
        st.caption(
            "현재는 로그인 없이 체험할 수 있습니다."
        )

    st.caption(
        "로그인 기록은 학습용 로컬 DB에 "
        "저장되며, 클라우드 재시작·재배포 시 "
        "사라질 수 있습니다."
    )


# -----------------------------------
# 7. 캐릭터 이동형 도서관
# -----------------------------------

st.subheader("🏛️ 도서관 둘러보기")

cols = st.columns(3)

for idx, col in enumerate(cols):
    with col:
        st.markdown(
            f"#### {ZONE_ICONS[idx]} "
            f"{ZONES[idx]} 책장"
        )

        st.image(
            make_shelf(
                idx,
                st.session_state.bm_position == idx,
            ),
            use_container_width=True,
        )

left, middle, right = st.columns(
    [1, 2, 1]
)

with left:
    if st.button(
        "◀ 왼쪽",
        disabled=(
            st.session_state.bm_position == 0
        ),
        use_container_width=True,
    ):
        st.session_state.bm_position -= 1
        st.session_state.bm_zone = None
        st.rerun()

with middle:
    position = st.session_state.bm_position

    if st.button(
        f"🚪 {ZONES[position]} 책장 이용하기",
        type="primary",
        use_container_width=True,
    ):
        st.session_state.bm_zone = position
        st.rerun()

with right:
    if st.button(
        "오른쪽 ▶",
        disabled=(
            st.session_state.bm_position == 2
        ),
        use_container_width=True,
    ):
        st.session_state.bm_position += 1
        st.session_state.bm_zone = None
        st.rerun()


# -----------------------------------
# 8. 활동할 책 선택
# -----------------------------------

st.divider()
st.subheader("📖 활동할 책 선택")

with st.form(
    "bm_book_input",
    clear_on_submit=True,
):
    c1, c2 = st.columns(2)

    with c1:
        title = st.text_input(
            "책 제목 *",
            max_chars=100,
        )

    with c2:
        author = st.text_input(
            "저자",
            max_chars=70,
        )

    do_book = st.form_submit_button(
        "이 책으로 활동하기"
    )

if do_book:
    if not title.strip():
        st.warning(
            "책 제목을 입력해 주세요."
        )

    else:
        k = book_key(
            title,
            author,
        )

        ok = write_db(
            """
            INSERT OR REPLACE INTO books(
                user_id, book_id, title, author
            )
            VALUES(?,?,?,?)
            """,
            (
                st.session_state.bm_user,
                k,
                title.strip(),
                author.strip(),
            ),
        )

        if ok:
            st.session_state.bm_books[k] = {
                "title": title.strip(),
                "author": author.strip(),
            }

            st.session_state.bm_book = k
            st.session_state.bm_bookmark = None
            st.rerun()

books = st.session_state.bm_books

if books:
    keys = list(books)
    current = st.session_state.bm_book

    chosen = st.selectbox(
        "내가 등록한 책",
        keys,
        index=(
            keys.index(current)
            if current in books
            else 0
        ),
        format_func=lambda key: (
            f"{books[key]['title']} · "
            f"{books[key]['author'] or '저자 미입력'}"
        ),
    )

    if chosen != st.session_state.bm_book:
        st.session_state.bm_book = chosen
        st.session_state.bm_bookmark = None
        st.rerun()

else:
    st.info(
        "책 제목을 등록한 후 책장으로 이동해 "
        "활동해 보세요."
    )

key = st.session_state.bm_book

if key is not None:
    book = books.get(key)
else:
    book = None

zone = st.session_state.bm_zone
user_id = st.session_state.bm_user


# -----------------------------------
# 9. 한줄평 / 독후감 / 책갈피
# -----------------------------------

if zone is None:
    st.info(
        "캐릭터를 이동해 원하는 책장의 "
        "'이용하기' 버튼을 눌러 주세요."
    )

elif book is None:
    st.info(
        "활동할 책을 먼저 등록해 주세요."
    )

elif zone == 0:
    # 한줄평
    st.subheader(
        f"💬 한줄평 · {book['title']}"
    )

    saved = st.session_state.bm_reviews.get(
        key,
        {},
    )

    with st.form(f"bm_review_{key}"):
        rating = st.slider(
            "별점",
            1,
            5,
            value=saved.get("rating", 3),
        )

        content = st.text_area(
            "한줄평 (10~100자)",
            value=saved.get("text", ""),
            max_chars=100,
        )

        save = st.form_submit_button(
            "한줄평 저장"
        )

    if save:
        if len(content.strip()) < 10:
            st.warning(
                "한줄평은 10자 이상 입력해 주세요."
            )

        elif write_db(
            """
            INSERT OR REPLACE INTO reviews(
                user_id, book_id, rating, content
            )
            VALUES(?,?,?,?)
            """,
            (
                user_id,
                key,
                rating,
                content.strip(),
            ),
        ):
            st.session_state.bm_reviews[key] = {
                "rating": rating,
                "text": content.strip(),
            }
            st.rerun()

    if saved:
        st.success(
            "⭐" * saved["rating"]
            + "  "
            + saved["text"]
        )

        if st.button("한줄평 삭제"):
            if write_db(
                """
                DELETE FROM reviews
                WHERE user_id=? AND book_id=?
                """,
                (user_id, key),
            ):
                st.session_state.bm_reviews.pop(
                    key,
                    None,
                )
                st.rerun()


elif zone == 1:
    # 독후감
    st.subheader(
        f"📝 독후감 · {book['title']}"
    )

    saved = st.session_state.bm_reports.get(
        key,
        {},
    )

    with st.form(f"bm_report_{key}"):
        reason = st.text_area(
            "1. 책을 읽게 된 이유",
            value=saved.get("reason", ""),
        )

        scene = st.text_area(
            "2. 가장 인상 깊었던 내용",
            value=saved.get("scene", ""),
        )

        thought = st.text_area(
            "3. 읽고 난 뒤의 생각",
            value=saved.get("thought", ""),
        )

        save = st.form_submit_button(
            "독후감 저장"
        )

    if save:
        if not all(
            part.strip()
            for part in (
                reason,
                scene,
                thought,
            )
        ):
            st.warning(
                "세 항목을 모두 작성해 주세요."
            )

        elif write_db(
            """
            INSERT OR REPLACE INTO reports(
                user_id, book_id, reason, scene, thought
            )
            VALUES(?,?,?,?,?)
            """,
            (
                user_id,
                key,
                reason.strip(),
                scene.strip(),
                thought.strip(),
            ),
        ):
            st.session_state.bm_reports[key] = {
                "reason": reason.strip(),
                "scene": scene.strip(),
                "thought": thought.strip(),
            }
            st.rerun()

    if saved:
        report = (
            f"[{book['title']}] 독후감\n\n"
            f"1. 읽게 된 이유\n"
            f"{saved['reason']}\n\n"
            f"2. 인상 깊었던 내용\n"
            f"{saved['scene']}\n\n"
            f"3. 읽고 난 뒤의 생각\n"
            f"{saved['thought']}"
        )

        st.text_area(
            "독후감 미리보기",
            report,
            height=250,
            disabled=True,
        )

        st.download_button(
            "📥 독후감 TXT 다운로드",
            report.encode("utf-8-sig"),
            file_name="bookmoa_report.txt",
            mime="text/plain",
        )

        if st.button("독후감 삭제"):
            if write_db(
                """
                DELETE FROM reports
                WHERE user_id=? AND book_id=?
                """,
                (user_id, key),
            ):
                st.session_state.bm_reports.pop(
                    key,
                    None,
                )
                st.rerun()


elif zone == 2:
    # 책갈피
    st.subheader(
        f"🔖 책갈피 만들기 · {book['title']}"
    )

    default_quote = (
        st.session_state.bm_reviews
        .get(key, {})
        .get("text", "")
    )

    quote = st.text_area(
        "책갈피 문장",
        value=default_quote,
        max_chars=100,
        key=f"bm_quote_{key}",
    )

    theme = st.selectbox(
        "책갈피 디자인",
        list(PALETTES),
        key="bm_palette",
    )

    if st.button(
        "책갈피 이미지 만들기",
        type="primary",
    ):
        if not quote.strip():
            st.warning(
                "책갈피에 넣을 문장을 "
                "입력해 주세요."
            )

        else:
            try:
                st.session_state.bm_bookmark = (
                    bookmark_png(
                        book["title"],
                        book["author"],
                        quote.strip(),
                        theme,
                    )
                )

                st.session_state.bm_bookmark_key = (
                    key
                )

                st.rerun()

            except (ValueError, OSError) as exc:
                st.error(
                    f"이미지 생성에 실패했습니다: {exc}"
                )

    if (
        st.session_state.bm_bookmark is not None
        and st.session_state.bm_bookmark_key == key
    ):
        st.image(
            st.session_state.bm_bookmark,
            width=260,
        )

        st.download_button(
            "📥 책갈피 PNG 다운로드",
            st.session_state.bm_bookmark,
            file_name="bookmoa_bookmark.png",
            mime="image/png",
        )


# -----------------------------------
# 10. 내 독서 기록
# -----------------------------------

st.divider()

with st.expander("📒 내 독서 기록 보기"):
    if not books:
        st.write(
            "등록한 책이 없습니다."
        )

    for k, item in books.items():
        st.markdown(
            f"**📖 {item['title']}**"
        )

        review = (
            st.session_state.bm_reviews.get(k)
        )

        if review:
            st.write(
                "⭐" * review["rating"],
                review["text"],
            )

        if k in st.session_state.bm_reports:
            st.write(
                "📝 독후감 작성 완료"
            )

    if user_id is None:
        st.caption(
            "체험 중 작성한 기록은 "
            "현재 접속에서만 유지됩니다."
        )

    else:
        st.caption(
            "로그인한 계정의 기록이며 "
            "서버 재시작 시 사라질 수 있습니다."
        )
