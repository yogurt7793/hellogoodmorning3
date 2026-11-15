        with signup_tab:
            with st.form("bm_signup_form"):
                new_name = st.text_input("새 아이디 (영문·숫자·_)")
                new_pw = st.text_input("새 비밀번호 (8자 이상)", type="password")
                new_pw_confirm = st.text_input("비밀번호 확인", type="password")
                signup_submit = st.form_submit_button("회원가입", use_container_width=True)
            if signup_submit:
                if new_pw != new_pw_confirm:
                    st.error("비밀번호가 일치하지 않습니다.")
                else:
                    message = register_user(new_name.strip(), new_pw)
                    if message:
                        st.error(message)
                    else:
                        st.success("가입 완료! 로그인 탭에서 로그인해 주세요.")
        st.caption("로그인하지 않아도 체험할 수 있지만 기록은 현재 접속 중에만 유지됩니다.")
    st.caption("학습용 로컬 DB입니다. 클라우드 서버가 재시작되면 계정과 기록이 사라질 수 있습니다.")


# ────────── 메인 화면 ──────────
st.title("📖 책모아 도서관")
st.caption("책장 사이를 이동하며 책에 대한 생각을 기록하고 나만의 책갈피를 만들어 보세요.")
st.markdown("### 🏛️ 도서관 둘러보기")

columns = st.columns(3, gap="small")
for index, col in enumerate(columns):
    with col:
        # 한글 제목은 이미지에 넣지 않고 Streamlit 자체 글자로 표시한다.
        st.markdown(f"#### {ICONS[index]} {ZONES[index]} 공간")
        st.image(draw_shelf(index, st.session_state.bm_position == index), use_container_width=True)

left, center, right = st.columns([1, 2, 1])
with left:
    if st.button("◀ 왼쪽 이동", disabled=st.session_state.bm_position == 0, use_container_width=True):
        st.session_state.bm_position -= 1
        st.session_state.bm_active = None
        st.rerun()
with center:
    current_zone = ZONES[st.session_state.bm_position]
    if st.button(f"🚪 {current_zone} 공간 입장", type="primary", use_container_width=True):
        st.session_state.bm_active = st.session_state.bm_position
        st.rerun()
with right:
    if st.button("오른쪽 이동 ▶", disabled=st.session_state.bm_position == 2, use_container_width=True):
        st.session_state.bm_position += 1
        st.session_state.bm_active = None
        st.rerun()

st.divider()
st.subheader("📘 활동할 책 선택")
with st.form("bm_book_form", clear_on_submit=True):
    col_title, col_author = st.columns(2)
    title = col_title.text_input("책 제목 *", max_chars=100)
    author = col_author.text_input("저자 (선택)", max_chars=70)
    submitted_book = st.form_submit_button("이 책으로 활동하기")
if submitted_book:
    if not title.strip():
        st.warning("책 제목을 입력해 주세요.")
    else:
        key = book_key(title, author)
        book = {"title": title.strip(), "author": author.strip()}
        st.session_state.bm_books[key] = book
        st.session_state.bm_current = key
        st.session_state.bm_png = None
        save_book(st.session_state.bm_user_id, key, book["title"], book["author"])
        st.rerun()

if st.session_state.bm_books:
    book_ids = list(st.session_state.bm_books)
    selected = st.selectbox(
        "등록한 책 목록", book_ids,
        index=book_ids.index(st.session_state.bm_current)
        if st.session_state.bm_current in book_ids else 0,
        format_func=lambda key: st.session_state.bm_books[key]["title"],
    )
    if selected != st.session_state.bm_current:
        if st.button("이 책 선택", use_container_width=True):
            st.session_state.bm_current = selected
            st.session_state.bm_png = None
            st.rerun()
else:
    st.info("책 제목을 입력하면 한줄평·독후감·책갈피를 만들 수 있습니다.")

book_id = st.session_state.bm_current
book = st.session_state.bm_books.get(book_id) if book_id else None
active = st.session_state.bm_active
user_id = st.session_state.bm_user_id

if active is None:
    st.info("캐릭터를 움직이고 '공간 입장'을 누르면 해당 활동이 열립니다.")
elif book is None:
    st.info("먼저 활동할 책을 등록해 주세요.")
else:
    st.divider()
    st.subheader(f"{ICONS[active]} {ZONES[active]} · {book['title']}")
    if active == 0:
        saved = st.session_state.bm_reviews.get(book_id, {})
        with st.form(f"bm_review_{book_id}"):
            rating = st.slider("별점", 1, 5, value=saved.get("rating", 3))
            content = st.text_area("한줄평 (10~100자)", value=saved.get("text", ""), max_chars=100)
            save_clicked = st.form_submit_button("한줄평 저장", type="primary")
        if save_clicked:
            if len(content.strip()) < 10:
                st.warning("한줄평은 10자 이상 작성해 주세요.")
            else:
                st.session_state.bm_reviews[book_id] = {"rating": rating, "text": content.strip()}
                save_review(user_id, book_id, rating, content.strip())
                st.rerun()
        if saved:
            st.success("⭐" * saved["rating"] + " " + saved["text"])
            if st.button("한줄평 삭제"):
                st.session_state.bm_reviews.pop(book_id, None)
                delete_record("reviews", user_id, book_id)
                st.rerun()

    elif active == 1:
        saved = st.session_state.bm_reports.get(book_id, {})
        with st.form(f"bm_report_{book_id}"):
            reason = st.text_area("1. 읽게 된 이유", value=saved.get("reason", ""), height=100)
            scene = st.text_area("2. 인상 깊었던 내용", value=saved.get("scene", ""), height=115)
            thought = st.text_area("3. 읽고 난 뒤의 생각", value=saved.get("thought", ""), height=115)
            save_clicked = st.form_submit_button("독후감 저장", type="primary")
        if save_clicked:
            if not all(part.strip() for part in (reason, scene, thought)):
                st.warning("세 항목을 모두 작성해 주세요.")
            else:
                clean = {"reason": reason.strip(), "scene": scene.strip(), "thought": thought.strip()}
                st.session_state.bm_reports[book_id] = clean
                save_report(user_id, book_id, **clean)
                st.rerun()
        if saved:
            full_text = (
                f"[{book['title']}] 독후감\n\n"
                f"1. 읽게 된 이유\n{saved['reason']}\n\n"
                f"2. 인상 깊었던 내용\n{saved['scene']}\n\n"
                f"3. 읽고 난 뒤의 생각\n{saved['thought']}"
            )
            st.text_area("저장된 독후감", value=full_text, height=250, disabled=True)
            st.download_button("📥 독후감 TXT 다운로드", full_text.encode("utf-8-sig"),
                               file_name="bookmoa_report.txt", mime="text/plain")
            if st.button("독후감 삭제"):
                st.session_state.bm_reports.pop(book_id, None)
                delete_record("reports", user_id, book_id)
                st.rerun()

    elif active == 2:
        review_text = st.session_state.bm_reviews.get(book_id, {}).get("text", "")
        quote = st.text_area("책갈피에 넣을 문장", value=review_text, max_chars=100,
                             key=f"bm_quote_{book_id}")
        theme = st.selectbox("디자인", list(THEMES), key="bm_theme")
        if st.button("책갈피 PNG 만들기", type="primary"):
            if not quote.strip():
                st.warning("책갈피에 넣을 문장을 작성해 주세요.")
            else:
                try:
                    st.session_state.bm_png = create_bookmark(
                        book["title"], book["author"], quote.strip(), theme
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        if st.session_state.bm_png:
            st.image(st.session_state.bm_png, width=280)
            st.download_button("📥 책갈피 PNG 다운로드", st.session_state.bm_png,
                               file_name="bookmoa_bookmark.png", mime="image/png")

st.divider()
with st.expander("📒 내 독서 기록 보기"):
    if not st.session_state.bm_books:
        st.write("아직 등록한 책이 없습니다.")
    else:
        for key, entry in st.session_state.bm_books.items():
            st.markdown(f"**📖 {entry['title']}**")
            if key in st.session_state.bm_reviews:
                item = st.session_state.bm_reviews[key]
                st.write("⭐" * item["rating"], item["text"])
            if key in st.session_state.bm_reports:
                st.write("📝 독후감 저장 완료")
    if user_id is None:
        st.caption("로그인하지 않은 기록은 브라우저 세션 종료 후 유지되지 않습니다.")
    else:
        st.caption("로그인한 계정의 기록입니다. 현재 서버의 로컬 DB에 저장됩니다.")
