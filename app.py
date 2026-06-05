import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
import re
import pandas as pd

# 팀별 테마 색상 정의
TEAM_CONFIG = {
    "국내영업팀": {"color": "#007BFF", "hover": "#0056b3", "icon": "🚚"},
    "해외영업팀": {"color": "#FF8C00", "hover": "#CC7000", "icon": "🚢"},
    "트랙영업팀": {"color": "#28A745", "hover": "#1E7E34", "icon": "🚜"}
}

# 1. 초기 카테고리 설정
if 'selected_team' not in st.session_state:
    st.session_state.selected_team = "국내영업팀"
    
selected_color = TEAM_CONFIG[st.session_state.selected_team]['color']

# 2. 팀별 색상 + 버튼 공통 CSS
st.markdown(f"""
<style>
    .team-container {{ display: flex; justify-content: center; gap: 15px; margin-bottom: 30px; }}
    .team-card {{
        flex: 1; text-align: center; padding: 15px; border-radius: 12px;
        color: white; font-weight: bold; cursor: pointer; transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 2px solid transparent;
    }}
    .btn-dom {{ background-color: {TEAM_CONFIG["국내영업팀"]["color"]}; }}
    .btn-dom:hover {{ background-color: {TEAM_CONFIG["국내영업팀"]["hover"]}; transform: translateY(-3px); box-shadow: 0 6px 12px rgba(0,0,0,0.2); }}
    .btn-int {{ background-color: {TEAM_CONFIG["해외영업팀"]["color"]}; }}
    .btn-int:hover {{ background-color: {TEAM_CONFIG["해외영업팀"]["hover"]}; transform: translateY(-3px); }}
    .btn-track {{ background-color: {TEAM_CONFIG["트랙영업팀"]["color"]}; }}
    .btn-track:hover {{ background-color: {TEAM_CONFIG["트랙영업팀"]["hover"]}; transform: translateY(-3px); }}

    /* ── 섹션 헤더 커스텀 스타일 ── */
    .section-header {{
        font-size: 17px !important; font-weight: 700 !important;
        color: var(--text-color) !important; margin: 4px 0 2px 0 !important;
        padding: 0 !important; line-height: 1.4 !important;
    }}
    .rainbow-divider {{
        height: 3px; border: none; border-radius: 2px;
        background: linear-gradient(90deg, #ff6b6b, #ffa500, #ffd700, #7ed957, #4fc3f7, #7c4dff);
        margin: 4px 0 14px 0;
    }}
    .sub-header {{
        font-size: 14px !important; font-weight: 600 !important;
        color: var(--text-color) !important; margin: 10px 0 6px 0 !important; opacity: 0.85;
    }}

    /* ══════════════════════════════════════════════════════
       사이드바 팀 선택 버튼: 컬럼 안 버튼만 타겟
       ══════════════════════════════════════════════════════ */
    [data-testid="stSidebar"] [data-testid="column"] button {{
        font-size: 11px !important;
        padding: 3px 1px !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        line-height: 1.2 !important;
    }}
    [data-testid="stSidebar"] [data-testid="column"] button p {{
        font-size: 11px !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        line-height: 1.2 !important;
        margin: 0 !important;
    }}

    /* ── 사이드바 전체 버튼 폰트 통일 (새 대화 시작 / 대화목록) ── */
    [data-testid="stSidebar"] button {{
        font-size: 13px !important;
    }}
    [data-testid="stSidebar"] button p {{
        font-size: 13px !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }}

    /* ══════════════════════════════════════════════════════
       휴지통 버튼: 🗑️ 단일 이모지를 가진 버튼 타겟
       Streamlit은 버튼 텍스트를 <p> 태그로 렌더링하므로
       p 텍스트 내용으로 식별 가능
       ══════════════════════════════════════════════════════ */
    button:has(p:only-child) {{
        /* 전체 영향 방지 */
    }}
    /* 🗑️ 이모지만 있는 버튼 → 프레임 제거 */
    [data-testid="stSidebar"] ~ div button:has(> div > p),
    div[data-testid="stButton"]:has(button:has(p)) button[data-testid="baseButton-secondary"] {{
        /* 기본 유지 */
    }}
</style>
""", unsafe_allow_html=True)

# ── 휴지통 버튼 전용 CSS (JS 없이 순수 CSS로 처리)
st.markdown("""
<style>
/* ────────────────────────────────────────────────────────────
   휴지통 버튼 스타일
   Streamlit secondary 버튼 중 텍스트가 매우 짧은(이모지 1개) 경우
   → 컬럼 비율을 충분히 줘서 잘리지 않게 하고
     버튼 자체도 overflow visible 처리
──────────────────────────────────────────────────────────── */

/* 모든 secondary 버튼의 p 태그 overflow 기본 허용 */
div[data-testid="stButton"] button[data-testid="baseButton-secondary"] p {
    overflow: visible !important;
    white-space: nowrap !important;
    line-height: 1.2 !important;
}

/* 버튼 자체도 overflow 허용 + flex 중앙 정렬 */
div[data-testid="stButton"] button[data-testid="baseButton-secondary"] {
    overflow: visible !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}

/* dom_del / trk_del / cb_del 버튼:
   Streamlit은 key를 버튼 부모 div의 data-testid에 노출하지 않지만
   aria-label(=help 파라미터) 없이 key만 있을 때
   가장 확실한 방법은 위의 overflow 허용만으로 충분함.
   추가로 테두리만 살짝 적용 */
div[data-testid="stHorizontalBlock"] > div:last-child
    div[data-testid="stButton"] button[data-testid="baseButton-secondary"] {
    border: 1px solid rgba(239,68,68,0.35) !important;
    border-radius: 6px !important;
    background: transparent !important;
    box-shadow: none !important;
    opacity: 0.7 !important;
    transition: opacity 0.15s ease !important;
}
div[data-testid="stHorizontalBlock"] > div:last-child
    div[data-testid="stButton"] button[data-testid="baseButton-secondary"]:hover {
    background: rgba(239,68,68,0.10) !important;
    border-color: rgba(239,68,68,0.7) !important;
    opacity: 1 !important;
}
div[data-testid="stHorizontalBlock"] > div:last-child
    div[data-testid="stButton"] button[data-testid="baseButton-secondary"]:disabled {
    opacity: 0.2 !important;
    border-color: rgba(128,128,128,0.2) !important;
}
</style>
""", unsafe_allow_html=True)

# --- 시뮬레이터 문의 팝업 ---
@st.dialog("📋 시뮬레이터 문의하기")
def show_simulator_inquiry_popup(simulator_type: str, sim_summary: str):
    """시뮬레이터 결과 기반 이메일 문의 팝업"""
    current_team = st.session_state.get("selected_team", "")

    st.markdown(
        f'''<div style="background:linear-gradient(135deg,rgba(59,130,246,0.08),rgba(16,185,129,0.08));
        border-left:4px solid #3b82f6;border-radius:8px;padding:12px 16px;
        margin-bottom:16px;font-size:13px;color:#374151;line-height:1.7;">
        <strong>[시뮬레이터 문의] {simulator_type}</strong><br>
        시뮬레이션 결과를 첨부해 담당자에게 문의 메일을 발송합니다.
        </div>''', unsafe_allow_html=True
    )

    author = st.text_input("✍️ 작성자", placeholder="이름을 입력하세요", max_chars=30)

    st.markdown("**📝 문의 내용**")
    default_content = f"[시뮬레이터 결과]\n{sim_summary}\n\n[추가 문의사항]\n"
    inquiry_text = st.text_area(
        label="문의 내용",
        value=default_content,
        height=180,
        max_chars=1000,
        label_visibility="collapsed"
    )

    st.markdown("")
    col_send, col_cancel = st.columns([1, 1])
    with col_send:
        if st.button("📨 문의 발송", use_container_width=True, type="primary"):
            if not author.strip():
                st.warning("작성자를 입력해주세요.")
            elif not inquiry_text.strip():
                st.warning("문의 내용을 입력해주세요.")
            else:
                try:
                    success = EMAIL_NOTIFIER.send_simulator_inquiry(
                        simulator_type=simulator_type,
                        team=current_team,
                        author=author.strip(),
                        content=inquiry_text.strip()
                    )
                except Exception:
                    success = False
                if success:
                    st.toast(f"✅ 문의가 담당자에게 전달되었습니다! ({author})", icon="📋")
                else:
                    st.toast("⚠️ 전송 실패. 이메일 설정(.env)을 확인해주세요.", icon="⚠️")
                st.rerun()
    with col_cancel:
        if st.button("취소", use_container_width=True):
            st.rerun()


# --- 부정 피드백 사유 팝업 ---
@st.dialog("💬 답변이 불만족스러우셨나요?")
def show_bad_feedback_popup(msg_idx: int, query: str, answer: str):
    """부정 피드백 사유 입력 팝업"""
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, rgba(239,68,68,0.08), rgba(251,191,36,0.08));
        border-left: 4px solid #ef4444;
        border-radius: 8px;
        padding: 14px 16px;
        margin-bottom: 18px;
        font-size: 14px;
        line-height: 1.7;
        color: #374151;
    ">
        여러분의 피드백은 <strong>AI 답변 품질 개선</strong>에 직접적으로 반영됩니다.<br>
        어떤 점이 불만족스러우셨는지 알려주시면 더 정확한 답변을 제공할 수 있습니다. 🙏
    </div>
    """, unsafe_allow_html=True)

    # ★ 작성자명
    bf_author = st.text_input("✍️ 작성자", placeholder="이름을 입력하세요", max_chars=30, key="bf_author")

    # 사유 선택 (체크박스)
    st.markdown("**불만족 이유를 선택해주세요** (복수 선택 가능)")
    reasons = {
        "wrong":    st.checkbox("❌ 답변 내용이 틀렸어요"),
        "missing":  st.checkbox("🔍 필요한 정보가 빠졌어요"),
        "unclear":  st.checkbox("😕 답변이 이해하기 어려워요"),
        "unrelated":st.checkbox("🚫 질문과 관련 없는 답변이에요"),
        "calc":     st.checkbox("🔢 계산이 잘못되었어요"),
    }
    REASON_LABELS = {
        "wrong": "답변 내용 오류",
        "missing": "정보 누락",
        "unclear": "내용 불명확",
        "unrelated": "질문 무관 답변",
        "calc": "계산 오류",
    }

    # 추가 의견
    extra = st.text_area(
        "추가 의견 (선택 사항)",
        placeholder="더 자세한 내용을 알려주시면 개선에 큰 도움이 됩니다.",
        max_chars=300,
        height=90
    )

    st.markdown("")
    col_submit, col_cancel = st.columns([1, 1])

    with col_submit:
        if st.button("📤 피드백 제출", use_container_width=True, type="primary"):
            if not bf_author.strip():
                st.warning("작성자를 입력해주세요.")
            else:
                selected = [REASON_LABELS[k] for k, v in reasons.items() if v]
                reason_text = " / ".join(selected) if selected else "사유 미입력"
                if extra.strip():
                    reason_text += f" | 추가의견: {extra.strip()}"
                reason_text = f"[작성자: {bf_author.strip()}] " + reason_text

                if (st.session_state.current_id, msg_idx) not in st.session_state.feedback_done:
                    submit_feedback(query, 0.0, answer, [], reason=reason_text)
                    st.session_state.feedback_done.add((st.session_state.current_id, msg_idx))

                st.toast(f"피드백이 반영되었습니다. 감사합니다! ({bf_author.strip()}) 🙏")
                st.rerun()

    with col_cancel:
        if st.button("취소", use_container_width=True):
            st.rerun()
@st.dialog("📄 참고 문서 미리보기")
def show_source_popup(sources: list, query: str):
    """참고 문서 팝업 - 키워드 하이라이트 포함"""
    if not sources:
        st.info("참고한 문서 정보가 없습니다.")
        return

    # 키워드 추출 (2글자 이상)
    keywords = [k for k in query.split() if len(k) >= 2]

    # 탭으로 문서 구분 (최대 3개)
    tab_labels = [f"📄 {s['name'][:15]}.." if len(s['name']) > 15 else f"📄 {s['name']}" for s in sources]
    tabs = st.tabs(tab_labels)

    for tab, source in zip(tabs, sources):
        with tab:
            content = source.get("content", "내용을 불러올 수 없습니다.")

            # 키워드 하이라이트 적용
            highlighted = content
            for kw in keywords:
                highlighted = re.sub(
                    f"({re.escape(kw)})",
                    r'<mark style="background-color:#FFE066;color:#333;padding:1px 3px;border-radius:3px;">\1</mark>',
                    highlighted,
                    flags=re.IGNORECASE
                )
            # 줄바꿈 → <br>
            highlighted = highlighted.replace("\n", "<br>")

            st.markdown(
                f"""
                <div style="
                    height: 420px; overflow-y: auto;
                    border: 1px solid #e2e8f0; border-radius: 10px;
                    padding: 16px 20px; background: #f8fafc;
                    color: #334155; line-height: 1.9; font-size: 14px;
                ">
                    {highlighted}
                </div>
                """,
                unsafe_allow_html=True
            )
            st.caption(f"🔍 하이라이트 키워드: {' · '.join(keywords) if keywords else '없음'}")

# ── 3D 헬퍼 함수 (전역) ─────────────────────────────────────────────────────

def _place_pallets(plt_w, plt_l, car_w, car_l, n_plt):
    """파렛트를 적재함에 배치한 (x,y) 좌표 목록 반환."""
    positions = []
    cols1 = int(car_w / plt_w) if plt_w <= car_w else 0
    cols2 = int(car_w / plt_l) if plt_l <= car_w else 0
    rows1 = int(car_l / plt_l) if cols1 else 0
    rows2 = int(car_l / plt_w) if cols2 else 0
    if cols1 * rows1 >= cols2 * rows2:
        pw, pl = plt_w, plt_l
        cols   = cols1
    else:
        pw, pl = plt_l, plt_w
        cols   = cols2
    if cols == 0:
        return positions
    placed = 0
    row_idx = 0
    while placed < n_plt:
        y0 = row_idx * pl
        if y0 + pl > car_l + 0.001:
            break
        for c in range(cols):
            if placed >= n_plt:
                break
            positions.append((c * pw, y0))
            placed += 1
        row_idx += 1
    return positions


def _make_box_trace(x, y, z, dx, dy, dz, name, color, opacity=0.75):
    """Mesh3d 박스 트레이스. '__hidden'으로 시작하면 범례 제외."""
    import plotly.graph_objects as go
    _hidden = name.startswith("__hidden")
    return go.Mesh3d(
        x=[x,x,x+dx,x+dx, x,x,x+dx,x+dx],
        y=[y,y+dy,y+dy,y, y,y+dy,y+dy,y],
        z=[z,z,z,z, z+dz,z+dz,z+dz,z+dz],
        i=[7,0,0,0,4,4,6,6,4,0,3,2],
        j=[3,4,1,2,5,6,5,2,0,1,6,3],
        k=[0,7,2,3,6,7,1,1,5,5,7,6],
        opacity=opacity,
        color=color,
        name="" if _hidden else name,
        showlegend=not _hidden,
        hovertemplate=(
            "<extra></extra>" if _hidden else
            f"<b>{name}</b><br>"
            f"위치: ({x:.2f}, {y:.2f}, {z:.2f})<br>"
            f"크기: {dx:.2f}m × {dy:.2f}m × {dz:.2f}m<extra></extra>"
        )
    )


def _make_wireframe(lx, ly, lz, color="#888888"):
    """적재함 외곽선(Wireframe) 12개 엣지 반환."""
    import plotly.graph_objects as go
    edges = [
        ([0,lx],[0,0],[0,0]),   ([0,lx],[ly,ly],[0,0]),
        ([0,0],[0,ly],[0,0]),   ([lx,lx],[0,ly],[0,0]),
        ([0,lx],[0,0],[lz,lz]), ([0,lx],[ly,ly],[lz,lz]),
        ([0,0],[0,ly],[lz,lz]), ([lx,lx],[0,ly],[lz,lz]),
        ([0,0],[0,0],[0,lz]),   ([lx,lx],[0,0],[0,lz]),
        ([0,0],[ly,ly],[0,lz]), ([lx,lx],[ly,ly],[0,lz]),
    ]
    return [
        go.Scatter3d(x=xs, y=ys, z=zs, mode="lines",
                     line=dict(color=color, width=2),
                     showlegend=False, hoverinfo="skip")
        for xs, ys, zs in edges
    ]


# ── 컨베어벨트 3D 팝업 ──────────────────────────────────────────────────────
@st.dialog("🎡 컨베어벨트 3D 적재 시각화", width="large")
def show_cb_3d_popup():
    """session_state["cb_3d_data"]에서 fig, guide_html을 읽어 렌더링."""
    data = st.session_state.get("cb_3d_data", {})
    if not data:
        st.warning("3D 데이터가 없습니다.")
        return
    st.markdown(data.get("guide_html", ""), unsafe_allow_html=True)
    st.plotly_chart(data["fig"], use_container_width=True)
    st.caption("💡 원통=컨베어벨트 롤 | 빨간점선=높이2.6m(로베드기준) | 마우스로 회전·확대")


# ── 3D 적재 시각화 팝업 ──────────────────────────────────────────────────────
@st.dialog("📦 3D 적재 시각화", width="large")
def show_3d_view_popup(trucks: list, resolved_items: list, mode: str = "truck"):
    """
    배차 시뮬레이터 결과를 3D 입체로 시각화.
    mode = "truck"     : 국내/크롤러 배차 결과
    mode = "container" : 해외 컨테이너 결과
    trucks: [{"name", "spec", "assigned_plt", "length", "width", ...}, ...]
    resolved_items: [{"code","name","plt_w","plt_l","pallets","qty"}, ...]
    """
    import plotly.graph_objects as go
    import math as _math

    # ── 차량/컨테이너 치수 DB ──────────────────────────────────────────────
    VEHICLE_HEIGHT = 2.2   # 일반 차량 적재함 높이(m) 고정
    PALLET_HEIGHT  = 1.0   # 파렛트 포함 자재 높이(m) 기본값

    # 컨테이너 내부 치수 (ISO 규격, 단위 m)
    CONTAINER_DIMS = {
        "20ft" : {"length": 5.899, "width": 2.348, "height": 2.390},
        "40ft" : {"length":12.034, "width": 2.348, "height": 2.390},
        "40HC" : {"length":12.034, "width": 2.348, "height": 2.695},
        "45ft" : {"length":13.555, "width": 2.348, "height": 2.695},
    }

    # ── 팔레트 색상 팔레트 ────────────────────────────────────────────────
    PALETTE = [
        "#4C9BE8","#F4845F","#63C9A8","#E8C34C","#A878D8",
        "#E87B8C","#5AC4D4","#C4A35A","#7BE878","#D48878",
    ]

    # ── 컨테이너 모드 ─────────────────────────────────────────────────────
    if mode == "container":
        if not trucks:
            st.warning("컨테이너 정보가 없습니다.")
            return

        cntr_type     = trucks[0].get("container_type", "40ft")
        dims          = CONTAINER_DIMS.get(cntr_type, CONTAINER_DIMS["40ft"])
        cl, cw, ch    = dims["length"], dims["width"], dims["height"]
        assigned_plt  = trucks[0].get("assigned_plt", 0)
        max_plt_cap   = trucks[0].get("max_plt_cap", assigned_plt)
        boxes_per_plt = trucks[0].get("boxes_per_plt", 20)
        box_layers    = trucks[0].get("box_layers", 1)
        box_type      = trucks[0].get("box_type", "박스")
        has_pkg       = trucks[0].get("has_pkg", False)

        plt_w = resolved_items[0].get("plt_w", 1.1) if resolved_items else 1.1
        plt_l = resolved_items[0].get("plt_l", 1.1) if resolved_items else 1.1
        # plt_h_override: 패키징 단위 높이 반영 (없으면 기본 PALLET_HEIGHT)
        _plt_total_h = trucks[0].get("plt_h_override", PALLET_HEIGHT)
        single_layer_h = _plt_total_h / box_layers

        all_positions    = _place_pallets(plt_w, plt_l, cw, cl, max_plt_cap)
        loaded_positions = all_positions[:assigned_plt]
        empty_positions  = all_positions[assigned_plt:]

        fig = go.Figure()
        for tr in _make_wireframe(cl, cw, ch):
            fig.add_trace(tr)
        fig.add_trace(go.Mesh3d(
            x=[0,cl,cl,0], y=[0,0,cw,cw], z=[0,0,0,0],
            i=[0,0], j=[1,2], k=[2,3],
            color="#AAAAAA", opacity=0.12, showlegend=False, hoverinfo="skip"
        ))

        # 적재된 파렛트 (단수 적용)
        for i, (px, py) in enumerate(loaded_positions):
            color = PALETTE[i % len(PALETTE)]
            for layer in range(box_layers):
                z0  = layer * single_layer_h
                lbl = f"PLT {i+1} {box_type}" + (f" {layer+1}단" if box_layers > 1 else "")
                fig.add_trace(_make_box_trace(
                    py, px, z0, plt_l, plt_w, single_layer_h,
                    name=lbl if layer == 0 else f"__hidden_l{i}_{layer}",
                    color=color, opacity=0.78
                ))

        # ── 2단 적재 구분선: 각 파렛트 위 1단/2단 경계에 수평선 표시 ──────
        if has_pkg and box_layers > 1:
            for i, (px, py) in enumerate(loaded_positions):
                # 1단과 2단 사이 경계 평면 (흰색 얇은 사각형 테두리)
                bz = single_layer_h   # 단 경계 z 높이
                # 경계선 4개 엣지 (직사각형)
                fig.add_trace(go.Scatter3d(
                    x=[py, py+plt_l, py+plt_l, py,       py],
                    y=[px, px,       px+plt_w,  px+plt_w, px],
                    z=[bz, bz,       bz,         bz,       bz],
                    mode="lines",
                    line=dict(color="rgba(255,255,255,0.85)", width=3),
                    name="__hidden_boundary",
                    showlegend=False, hoverinfo="skip"
                ))

        # (2) 여유 공간 반투명 회색 표시
        for j, (px, py) in enumerate(empty_positions):
            fig.add_trace(_make_box_trace(
                py, px, 0, plt_l, plt_w, PALLET_HEIGHT,
                name="여유 공간" if j == 0 else "__hidden_empty",
                color="#CCCCCC", opacity=0.18
            ))

        rem_plt   = max_plt_cap - assigned_plt
        ratio_pct = (assigned_plt / max_plt_cap * 100) if max_plt_cap else 0
        stack_txt = (f"{box_layers}단 적재 (패키징)" if has_pkg and box_layers > 1
                     else f"{box_layers}단 적재" if box_layers > 1 else "1단 적재")
        # 2단 표시용 배지 HTML
        pkg_badge = (
            f'<span style="display:inline-block;margin-left:4px;padding:1px 7px;'
            f'border-radius:10px;font-size:10px;font-weight:700;'
            f'background:rgba(139,92,246,0.18);color:#7c3aed;">📦 {box_layers}단</span>'
            if has_pkg and box_layers > 1 else ""
        )

        # ── CBM 계산 ────────────────────────────────────────────────────────
        # 1) 컨테이너 총 용적 (m³)
        cntr_total_cbm = cl * cw * ch

        # 2) 파렛트 1개 부피: 가로 × 세로 × 높이(패키징 포함 전체 높이)
        plt_cbm_each   = plt_w * plt_l * _plt_total_h

        # 3) 적재 화물 총 CBM
        cargo_cbm      = plt_cbm_each * assigned_plt

        # 4) CBM 적재율 (화물 CBM / 컨테이너 총 CBM)
        cbm_ratio      = (cargo_cbm / cntr_total_cbm * 100) if cntr_total_cbm else 0

        # 5) 여유 CBM
        rem_cbm        = cntr_total_cbm - cargo_cbm

        fig.update_layout(
            scene=dict(
                xaxis=dict(range=[0, cl], title="길이 (m)"),
                yaxis=dict(range=[0, cw], title="폭 (m)"),
                zaxis=dict(range=[0, ch], title="높이 (m)"),
                aspectmode="manual",
                aspectratio=dict(x=cl/cw, y=1, z=ch/cw),
                camera=dict(eye=dict(x=1.6, y=-1.8, z=1.3))
            ),
            margin=dict(l=0, r=0, b=0, t=30),
            legend=dict(font=dict(size=11), x=0, y=1)
        )

        # ── 정보 카드 (1행: 컨테이너 / 적재PLT / 여유공간 / 적재방식) ──────
        info_html = (
            '<div style="display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap;">'
            + '<div style="flex:1;min-width:100px;background:var(--secondary-background-color);'
              'border-radius:8px;padding:8px 12px;border:1.5px solid rgba(128,128,128,0.15);">'
              '<div style="font-size:11px;opacity:0.6;color:var(--text-color);">컨테이너</div>'
              f'<div style="font-size:14px;font-weight:700;color:var(--text-color);">{cntr_type}</div>'
              f'<div style="font-size:11px;opacity:0.5;color:var(--text-color);">{cl}×{cw}×{ch}m</div></div>'
            + '<div style="flex:1;min-width:100px;background:rgba(59,130,246,0.08);'
              'border-radius:8px;padding:8px 12px;border:1.5px solid rgba(59,130,246,0.2);">'
              '<div style="font-size:11px;opacity:0.6;color:var(--text-color);">적재 PLT</div>'
              f'<div style="font-size:14px;font-weight:700;color:var(--text-color);">{assigned_plt} / {max_plt_cap} PLT</div>'
              f'<div style="font-size:11px;color:#3b82f6;">{ratio_pct:.0f}% 사용</div></div>'
            + '<div style="flex:1;min-width:100px;background:rgba(128,128,128,0.06);'
              'border-radius:8px;padding:8px 12px;border:1.5px solid rgba(128,128,128,0.15);">'
              '<div style="font-size:11px;opacity:0.6;color:var(--text-color);">여유 공간</div>'
              f'<div style="font-size:14px;font-weight:700;color:var(--text-color);">{rem_plt} PLT 여유</div>'
              f'<div style="font-size:11px;opacity:0.5;color:var(--text-color);">≈ {int(rem_plt * boxes_per_plt)}박스 추가 가능</div></div>'
            + '<div style="flex:1;min-width:100px;background:var(--secondary-background-color);'
              'border-radius:8px;padding:8px 12px;border:1.5px solid rgba(128,128,128,0.15);">'
              '<div style="font-size:11px;opacity:0.6;color:var(--text-color);">적재 방식</div>'
              f'<div style="font-size:14px;font-weight:700;color:var(--text-color);">{stack_txt}{pkg_badge}</div>'
              f'<div style="font-size:11px;opacity:0.5;color:var(--text-color);">PLT당 {boxes_per_plt}박스</div></div>'
            + '</div>'
        )

        # ── CBM 카드 (2행) ───────────────────────────────────────────────────
        cbm_color  = "#16a34a" if cbm_ratio <= 85 else ("#b45309" if cbm_ratio <= 100 else "#dc2626")
        cbm_bg     = ("rgba(34,197,94,0.08)" if cbm_ratio <= 85
                      else "rgba(234,179,8,0.08)" if cbm_ratio <= 100
                      else "rgba(239,68,68,0.08)")
        cbm_border = ("rgba(34,197,94,0.25)" if cbm_ratio <= 85
                      else "rgba(234,179,8,0.25)" if cbm_ratio <= 100
                      else "rgba(239,68,68,0.25)")

        cbm_html = (
            '<div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;">'
            # 화물 CBM
            + f'<div style="flex:1;min-width:100px;background:{cbm_bg};'
              f'border-radius:8px;padding:8px 12px;border:1.5px solid {cbm_border};">'
              '<div style="font-size:11px;opacity:0.6;color:var(--text-color);">📦 화물 CBM</div>'
              f'<div style="font-size:16px;font-weight:700;color:{cbm_color};">{cargo_cbm:.2f} m³</div>'
              f'<div style="font-size:11px;opacity:0.5;color:var(--text-color);">PLT 1개 = {plt_cbm_each:.3f} m³</div></div>'
            # 컨테이너 총 CBM
            + '<div style="flex:1;min-width:100px;background:var(--secondary-background-color);'
              'border-radius:8px;padding:8px 12px;border:1.5px solid rgba(128,128,128,0.15);">'
              '<div style="font-size:11px;opacity:0.6;color:var(--text-color);">🚢 컨테이너 총 용적</div>'
              f'<div style="font-size:16px;font-weight:700;color:var(--text-color);">{cntr_total_cbm:.2f} m³</div>'
              f'<div style="font-size:11px;opacity:0.5;color:var(--text-color);">내부 {cl}×{cw}×{ch}m 기준</div></div>'
            # CBM 적재율
            + f'<div style="flex:1;min-width:100px;background:{cbm_bg};'
              f'border-radius:8px;padding:8px 12px;border:1.5px solid {cbm_border};">'
              '<div style="font-size:11px;opacity:0.6;color:var(--text-color);">📊 CBM 적재율</div>'
              f'<div style="font-size:16px;font-weight:700;color:{cbm_color};">{cbm_ratio:.1f}%</div>'
              f'<div style="font-size:11px;opacity:0.5;color:var(--text-color);">여유 {rem_cbm:.2f} m³ 남음</div></div>'
            + '</div>'
        )

        st.markdown(info_html, unsafe_allow_html=True)
        st.markdown(cbm_html, unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True)
        _caption = "💡 회색 반투명 = 여유 공간 | 마우스로 회전·확대 | 범례 클릭으로 항목 숨기기"
        if has_pkg and box_layers > 1:
            _caption += f" | ─── 흰 경계선 = 1단·2단 구분 (패키징 {box_layers}단)"
        st.caption(_caption)
        return

    # ── 차량 배차 모드 ────────────────────────────────────────────────────
    valid_trucks = [t for t in trucks if not t.get("is_lowbed")]
    if not valid_trucks:
        st.warning("로베드 특수차량은 3D 시각화가 지원되지 않습니다.")
        return

    # 분할 배차 시 탭으로 차량 선택
    if len(valid_trucks) > 1:
        tab_labels = [f"🚚 차량 {i+1}: {t['name']}" for i, t in enumerate(valid_trucks)]
        tabs = st.tabs(tab_labels)
    else:
        tabs = [st.container()]

    for t_idx, (tab, truck) in enumerate(zip(tabs, valid_trucks)):
        with tab:
            # 적재함 치수 파싱 (spec: "길이 9.0m / 폭 2.34m")
            import re as _re
            spec = truck.get("spec", "길이 6.2m / 폭 2.34m")
            ln = _re.search(r'길이\s*([\d.]+)m', spec)
            wn = _re.search(r'폭\s*([\d.]+)m',  spec)
            car_l = float(ln.group(1)) if ln else 6.2
            car_w = float(wn.group(1)) if wn else 2.34
            car_h = VEHICLE_HEIGHT

            assigned_plt = truck.get("assigned_plt", 0)

            # 자재별로 비례 PLT 배분
            total_all_plt = sum(r.get("pallets", 0) for r in resolved_items) or 1
            item_assignments = []
            remain = assigned_plt
            for ri, r in enumerate(resolved_items):
                if ri == len(resolved_items) - 1:
                    n = remain
                else:
                    n = max(1, round(r.get("pallets", 0) / total_all_plt * assigned_plt))
                    n = min(n, remain)
                item_assignments.append({
                    **r, "truck_plt": n,
                    "plt_w": r.get("plt_w", 1.0),
                    "plt_l": r.get("plt_l", 1.1),
                })
                remain -= n
                if remain <= 0:
                    break

            # 3D 그리기
            fig = go.Figure()
            for tr in _make_wireframe(car_l, car_w, car_h, "#888888"):
                fig.add_trace(tr)
            # 바닥면
            fig.add_trace(go.Mesh3d(
                x=[0,car_l,car_l,0], y=[0,0,car_w,car_w], z=[0,0,0,0],
                i=[0,0], j=[1,2], k=[2,3],
                color="#CCCCCC", opacity=0.12, showlegend=False, hoverinfo="skip"
            ))

            # 자재별 파렛트 배치 (Y=폭 방향, X=길이 방향)
            cur_x = 0.0   # 길이 방향 현재 위치
            for ri, ia in enumerate(item_assignments):
                pw, pl = ia["plt_w"], ia["plt_l"]
                n = ia["truck_plt"]
                if n <= 0:
                    continue
                color = PALETTE[ri % len(PALETTE)]
                label = f"{ia.get('code','?')} ({ia.get('name','자재')[:10]})"

                # 이 자재의 파렛트 배치 (남은 적재함 길이 기준)
                remain_l = car_l - cur_x
                positions = _place_pallets(pw, pl, car_w, remain_l, n)

                for i, (px, py) in enumerate(positions):
                    fig.add_trace(_make_box_trace(
                        cur_x + py, px, 0,
                        pl, pw, PALLET_HEIGHT,
                        name=label if i == 0 else f"__hidden_{ri}_{i}",
                        color=color,
                    ))

                # 자재가 차지한 길이 만큼 cur_x 진행
                if positions:
                    max_y = max(py for _, py in positions)
                    orient_l = pl if (int(car_w / pw) >= 1) else pw
                    cur_x += max_y + orient_l

            # ── 국내 도로 화물 가이드라인 표시 ──────────────────────────
            # 국내 도로법 기준
            # - 최대 높이: 4.0m (지상 기준, 적재함 기준 ~2.5m)
            # - 최대 폭: 2.5m (적재함 기준 ~2.34m)
            # - 높이 2.6m 이상: 로베드 차량 필요
            GUIDE_H_LOWBED  = 2.6   # 로베드 기준 높이
            GUIDE_H_LEGAL   = 4.0   # 도로법 최대 높이 (지상 기준, 표시용)
            GUIDE_W_5TON    = 2.0   # 5톤 이상 폭 기준
            GUIDE_W_MAX     = 2.5   # 도로법 최대 폭

            # 가이드라인: 높이 2.6m 면 (로베드 기준) - 빨간 점선 평면
            gl = car_l
            # 높이 2.6m 수평선 (x방향 앞뒤)
            if GUIDE_H_LOWBED <= car_h + 0.5:
                fig.add_trace(go.Scatter3d(
                    x=[0, gl, gl, 0, 0],
                    y=[0, 0, car_w, car_w, 0],
                    z=[GUIDE_H_LOWBED]*5,
                    mode="lines",
                    line=dict(color="#ef4444", width=3, dash="dash"),
                    name="⚠️ 높이 2.6m (로베드 기준)",
                    showlegend=True,
                    hoverinfo="name"
                ))

            # 폭 2.0m 수직선 (5톤 이상 폭 기준)
            if GUIDE_W_5TON <= car_w:
                fig.add_trace(go.Scatter3d(
                    x=[0, gl], y=[GUIDE_W_5TON, GUIDE_W_5TON], z=[0, 0],
                    mode="lines",
                    line=dict(color="#f59e0b", width=2, dash="dot"),
                    name="폭 2.0m (5톤↑ 기준)",
                    showlegend=True, hoverinfo="name"
                ))
                fig.add_trace(go.Scatter3d(
                    x=[0, gl], y=[GUIDE_W_5TON, GUIDE_W_5TON], z=[car_h, car_h],
                    mode="lines",
                    line=dict(color="#f59e0b", width=2, dash="dot"),
                    name="__hidden_w_top",
                    showlegend=False, hoverinfo="skip"
                ))

            # 레이아웃
            a_wkg = truck.get("assigned_weight_kg", 0)
            rv    = truck.get("load_ratio_vol", 0)
            fig.update_layout(
                scene=dict(
                    xaxis=dict(range=[0, car_l], title="길이 (m)"),
                    yaxis=dict(range=[0, car_w], title="폭 (m)"),
                    zaxis=dict(range=[0, max(car_h, GUIDE_H_LOWBED + 0.1)], title="높이 (m)"),
                    aspectmode="manual",
                    aspectratio=dict(x=car_l/car_w, y=1, z=car_h/car_w),
                    camera=dict(eye=dict(x=1.5, y=-1.8, z=1.2))
                ),
                margin=dict(l=0,r=0,b=0,t=30),
                legend=dict(font=dict(size=11), x=0, y=1)
            )

            # 가이드라인 안내 카드
            guide_html = (
                '<div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap;">'
                + '<div style="flex:1;min-width:120px;background:rgba(239,68,68,0.08);border-radius:8px;'
                  'padding:7px 12px;border:1.5px solid rgba(239,68,68,0.25);">'
                  '<div style="font-size:11px;font-weight:700;color:#ef4444;">⚠️ 로베드 기준</div>'
                  '<div style="font-size:12px;color:var(--text-color);">높이 <b>2.6m 이상</b> → 로베드 차량</div>'
                  '<div style="font-size:11px;opacity:0.6;color:var(--text-color);">3D 내 빨간 점선</div></div>'
                + '<div style="flex:1;min-width:120px;background:rgba(245,158,11,0.08);border-radius:8px;'
                  'padding:7px 12px;border:1.5px solid rgba(245,158,11,0.25);">'
                  '<div style="font-size:11px;font-weight:700;color:#f59e0b;">📏 폭 기준</div>'
                  '<div style="font-size:12px;color:var(--text-color);"><b>2.0m↑</b> : 5톤~25톤/트레일러<br>'
                  f'현재 적재함: <b>{car_w}m</b></div>'
                  '<div style="font-size:11px;opacity:0.6;color:var(--text-color);">3D 내 주황 점선</div></div>'
                + '<div style="flex:1;min-width:120px;background:rgba(59,130,246,0.08);border-radius:8px;'
                  'padding:7px 12px;border:1.5px solid rgba(59,130,246,0.2);">'
                  '<div style="font-size:11px;font-weight:700;color:#3b82f6;">🚛 도로법 기준</div>'
                  '<div style="font-size:12px;color:var(--text-color);">최대 높이 <b>4.0m</b><br>최대 폭 <b>2.5m</b><br>최대 길이 <b>16.7m</b></div></div>'
                + '</div>'
            )
            st.markdown(
                f"**{truck['name']}** | 적재함 {car_l}×{car_w}×{car_h}m | "
                f"배정 {assigned_plt}PLT / {a_wkg:,.0f}kg | "
                f"부피 적재율 **{rv:.1f}%**"
            )
            st.markdown(guide_html, unsafe_allow_html=True)
            st.plotly_chart(fig, use_container_width=True)
            st.caption("💡 빨간 점선=높이 2.6m(로베드 기준) | 주황 점선=폭 2.0m | 마우스로 회전·확대 가능")

# --- RAG 인터페이스 연결(모듈화) ---
# try:
#     from main import LogisticsAgent
#     import logging
#     logger = logging.getLogger(__name__)
#     # 세션 상태에 에이전트 초기화 (싱글톤처럼 유지)
#     if "agent" not in st.session_state:
#         st.session_state.agent = LogisticsAgent()
    
#     # 기존 함수들과 호환되도록 래퍼(Wrapper) 함수 생성
#     def get_rag_response(query, context=None):
#         return st.session_state.agent.ask(query, context)

#     def submit_feedback(query, score, answer="", sources=[]):
#         st.session_state.agent.feedback(query, answer, score)

# except ImportError as e:
#     st.error(f"모듈을 불러오지 못했습니다: {e}")
#     def get_rag_response(q, context=None): return {"answer": "시스템 오류", "sources": []}
#     def submit_feedback(q, s, a, src): pass
#     import logging
#     logger = logging.getLogger(__name__)

# RAG 인터페이스 연결
try:
    from rag_pipeline.query_processor import get_rag_response, submit_feedback, analyze_logistics_data, analyze_pdf_logistics, get_db_transport_advice, get_split_dispatch_advice, EMAIL_NOTIFIER, get_freight_meta, calculate_fare_comparison, record_simulator_count, record_doc_click, record_sim_inquiry
    import logging
    logger = logging.getLogger(__name__)
except ImportError:
    def get_rag_response(q, context=None, team=""): return {"answer": "답변입니다.", "has_table": False}
    def submit_feedback(q, s, c, src, reason="", team=""): pass
    def get_db_transport_advice(p, w=0): return None
    def get_split_dispatch_advice(items): return {"trucks": [], "total_plt": 0, "total_weight_kg": 0, "split": False, "error": "모듈 미연결"}
    def get_freight_meta(): return {"loaded": False}
    def calculate_fare_comparison(dest, weight_kg): return {"직송": None, "화물": None, "택배": None, "추천": None}
    def record_simulator_count(simulator, team=""): pass
    def record_doc_click(answer_id): pass
    def record_sim_inquiry(simulator, team=""): pass
    def get_direct_fare(origin, dest, vehicle): return None
    def get_direct_fare_clauses(): return []
    def get_parcel_fare(region, kind, product, weight_kg): return None
    def get_freight_meta(): return {}
    class _DummyNotifier:
        enabled = False
        def send_improvement_request(self, content, team): return False
        def send_simulator_inquiry(self, simulator_type, team, author, content): return False
    EMAIL_NOTIFIER = _DummyNotifier()
    import logging
    logger = logging.getLogger(__name__)

load_dotenv()

st.set_page_config(
    page_title="LOGIBOT-DRB",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"  # 사이드바 시작부터 펼침
)

# --- CSS 스타일 ---
st.markdown("""
    <style>
    /* 기본 채팅 버블 */
    .chat-bubble {
        max-width: 85%; padding: 16px 20px; border-radius: 14px;
        margin-bottom: 12px; line-height: 1.6; font-size: 14px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .chat-bubble.user {
        background: rgba(59, 130, 246, 0.15); color: #3b82f6; 
        margin-left: auto; border-left: 4px solid #3b82f6;
    }
    .chat-bubble.assistant {
        background: rgba(148, 163, 184, 0.1); color: inherit; 
        margin-right: auto; border-left: 4px solid #10b981;
        border: 1px solid rgba(148, 163, 184, 0.2);
    }   
    
    /* 답변 컨테이너 */
    .answer-container {
        width: 100%;
    }
    
    /* 핵심 요약 */
    .answer-summary {
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.12), rgba(16, 185, 129, 0.12));
        padding: 14px 18px; border-radius: 12px; 
        border-left: 4px solid #3b82f6;
        font-weight: 600; margin-bottom: 14px;
        font-size: 15px; line-height: 1.6;
    }
    
    /* 세부 내용 */
    .answer-details {
        background: rgba(248, 250, 252, 0.5);
        padding: 14px 18px; border-radius: 10px;
        border: 1px solid rgba(226, 232, 240, 0.6);
        margin-top: 12px;
    }
    .detail-item {
        padding: 6px 0;
        border-bottom: 1px solid rgba(226, 232, 240, 0.3);
        line-height: 1.6;
        font-size: 14px;
    }
    .detail-item strong { 
        color: #1e40af; 
        margin-right: 6px; 
        font-size: 14px;
        display: inline-block;
    }
    
    /* 추천 질문 스타일 */
    .suggestion-container {
        background: linear-gradient(135deg, rgba(236, 254, 255, 0.8), rgba(254, 249, 195, 0.8));
        padding: 20px;
        border-radius: 16px;
        margin: 20px 0;
        border: 2px solid rgba(6, 182, 212, 0.3);
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .suggestion-title {
        font-size: 18px;
        font-weight: 700;
        color: #0e7490;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 사이드바 고정 CSS ---
st.markdown("""
    <style>
    /* 사이드바 드래그 리사이즈 핸들 비활성화 */
    [data-testid="stSidebarResizeHandle"],
    .st-emotion-cache-1cypcdb,
    div[class*="resizeHandle"],
    div[class*="ResizeHandle"] {
        display: none !important;
        pointer-events: none !important;
    }
    /* 사이드바 너비 고정 (expanded 상태 기준) */
    [data-testid="stSidebar"] {
        min-width: 21rem !important;
        max-width: 21rem !important;
        width: 21rem !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        min-width: 21rem !important;
        max-width: 21rem !important;
        width: 21rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 추천 질문 데이터 ---
TEAM_SUGGESTIONS = {
    "국내영업팀": [
        "국내 배차 신청 방법(수동/자동)",
        "주문 마감 시간",
        "내수용 PLT 규격 리스트",
        "부산 지입기사 정보",
        "물류팀 주문 가능 시간대",
        "국내 담당자에 대한 정보"
    ],
    "해외영업팀": [
        "수출 포장량 계산 기준",
        "컨테이너 적재 시뮬레이션",
        "수출용 BOX 종류",
        "샘플 보내는 방법",
        "컨베어벨트 직경을 구하는 방법",
        "수출 선적 서류 준비 리스트"
    ],
    "트랙영업팀": [
        "RT 종류별 적재 용량",
        "RT 배차 시뮬레이션",
        "RT 포장 규격",
        "RT 지게차 지원하는 방법",
        "배차 차량별 제원",
        "크롤러 담당자 정보"
    ]
}

# --- 세션 상태 초기화 ---
def _init_team_conv(team: str) -> dict:
    """팀 전용 초기 대화 생성"""
    greet = {
        "국내영업팀": "안녕하세요! 🚚 국내영업팀 전용 DRB 물류 AI입니다. 무엇을 도와드릴까요?",
        "해외영업팀": "안녕하세요! 🚢 해외영업팀 전용 DRB 물류 AI입니다. 무엇을 도와드릴까요?",
        "트랙영업팀": "안녕하세요! 🚜 트랙영업팀 전용 DRB 물류 AI입니다. 무엇을 도와드릴까요?",
    }
    return {
        "init": {
            "title": "새 대화",
            "messages": [{
                "role": "assistant",
                "content": greet.get(team, "안녕하세요! DRB 물류 AI입니다."),
                "timestamp": datetime.now().isoformat(),
                "has_table": False
            }],
            "context": []
        }
    }

if "team_conversations" not in st.session_state:
    st.session_state.team_conversations = {
        t: _init_team_conv(t) for t in ["국내영업팀", "해외영업팀", "트랙영업팀"]
    }

if "team_current_id" not in st.session_state:
    st.session_state.team_current_id = {
        t: "init" for t in ["국내영업팀", "해외영업팀", "트랙영업팀"]
    }

if "conversations" not in st.session_state:
    # 하위 호환: 기존 conversations 키 → 현재 팀 세션으로 연결
    st.session_state.conversations = st.session_state.team_conversations[
        st.session_state.get("selected_team", "국내영업팀")
    ]
    st.session_state.current_id = st.session_state.team_current_id[
        st.session_state.get("selected_team", "국내영업팀")
    ]

if "feedback_done" not in st.session_state:
    st.session_state.feedback_done = set()
if "editing_id" not in st.session_state:
    st.session_state.editing_id = None
if "pending_query" not in st.session_state:
    st.session_state.pending_query = None
if "show_suggestions" not in st.session_state:
    st.session_state.show_suggestions = True
# 비동기 보호 플래그
if "is_generating" not in st.session_state:
    st.session_state.is_generating = False   # LLM 호출 중 여부
if "queued_query" not in st.session_state:
    st.session_state.queued_query = None     # 생성 중 들어온 질문 대기열

def extract_table_from_text(text: str) -> tuple:
    """
    텍스트에서 마크다운 표를 모두 찾아 HTML 표로 변환.
    반환: (변환된 전체 HTML 텍스트, None)  — DataFrame은 더 이상 사용하지 않음.
    """
    import re as _re

    def render_one_table(table_lines: list) -> str:
        """마크다운 표 줄 목록 → HTML <table> (** 제거 + 결론 강조 포함)"""
        rows = [l for l in table_lines
                if l.strip() and not _re.match(r'^\s*\|[\s\-:|]+\|\s*$', l)]
        if not rows:
            return ""

        def _clean_cell(text: str) -> str:
            """셀 내 마크다운 변환 — ** → <strong>, * → <em>, ` → <code>"""
            text = _re.sub(r'\*\*([^*\n]+)\*\*', r'<strong>\1</strong>', text)
            text = _re.sub(r'\*([^*\n]+)\*',       r'<em>\1</em>',          text)
            text = _re.sub(r'`([^`]+)`',               r'<code>\1</code>',      text)
            return text.strip()

        # 결론/추천 행 감지 키워드
        HIGHLIGHT_KW = ['추천', '결론', '최적', '권장', '✅', '⭐', '→']

        html = (
            '<div style="overflow-x:auto;margin:12px 0;">'
            '<table style="border-collapse:collapse;width:100%;font-size:13px;'
            'border-radius:8px;overflow:hidden;">'
        )
        for i, row in enumerate(rows):
            cells = [_clean_cell(c) for c in row.strip().strip('|').split('|')]
            tag = 'th' if i == 0 else 'td'
            is_highlight = i > 0 and any(kw in row for kw in HIGHLIGHT_KW)
            if i == 0:
                cell_style = (
                    'background:rgba(99,102,241,0.8);color:#ffffff;'
                    'padding:9px 14px;text-align:left;font-weight:700;'
                    'white-space:nowrap;font-size:12px;letter-spacing:0.3px;'
                )
            elif is_highlight:
                # 결론/추천 행 강조
                cell_style = (
                    'background:rgba(16,185,129,0.12);'
                    'padding:8px 14px;border-bottom:1px solid rgba(16,185,129,0.3);'
                    'vertical-align:middle;font-weight:600;'
                )
            else:
                bg = 'rgba(0,0,0,0.025)' if i % 2 == 0 else 'transparent'
                cell_style = (
                    f'background:{bg};padding:8px 14px;'
                    'border-bottom:1px solid rgba(148,163,184,0.2);vertical-align:middle;'
                )
            html += '<tr>' + ''.join(
                f'<{tag} style="{cell_style}">{c}</{tag}>' for c in cells
            ) + '</tr>'
        html += '</table></div>'
        return html

    # 표 블록 전체를 HTML로 교체
    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # 표 시작 감지 (|로 시작하거나 다음 줄이 구분선)
        is_table_row = '|' in line and line.strip().startswith('|')
        next_is_sep  = (i + 1 < len(lines) and
                        _re.match(r'^\s*\|[\s\-:|]+\|\s*$', lines[i + 1]))
        if is_table_row or next_is_sep:
            # 표 블록 수집
            table_buf = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                table_buf.append(lines[i])
                i += 1
            html_table = render_one_table(table_buf)
            if html_table:
                result.append(html_table)
            else:
                result.extend(table_buf)  # 변환 실패 시 원문 유지
            continue
        result.append(line)
        i += 1

    return None, '\n'.join(result)   # DataFrame 자리는 None


# 결론/추천 강조 키워드
_CONCLUSION_KW = ['✅', '추천', '결론', '최적', '권장', '→ ', '⭐', '최종']

def md_to_html_answer(text: str) -> str:
    """
    LLM 마크다운 답변 → chat-bubble HTML 변환.
    - 표: extract_table_from_text가 이미 HTML로 변환
    - 헤더: 레벨별 스타일 차별화
    - 결론/추천 문장: 초록 배경 박스로 강조
    - **bold** / 리스트 / 구분선 / 줄바꿈 처리
    """
    import re as _re

    lines = text.split('\n')
    result_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # HTML 태그 줄 → 그대로 통과
        if line.strip().startswith('<') and '>' in line:
            result_lines.append(line)
            i += 1
            continue

        # 헤더 — 레벨별 스타일 차별화
        h = _re.match(r'^(#{1,3})\s+(.+)$', line)
        if h:
            level = len(h.group(1))
            if level == 1:
                style = ('font-size:1.2em;font-weight:800;margin:16px 0 8px;'
                         'border-left:4px solid rgba(99,102,241,0.8);padding-left:10px;')
            elif level == 2:
                style = ('font-size:1.05em;font-weight:700;margin:14px 0 6px;'
                         'border-bottom:2px solid rgba(99,102,241,0.35);padding-bottom:4px;')
            else:
                style = 'font-size:0.97em;font-weight:700;margin:10px 0 4px;color:inherit;'
            result_lines.append(f'<div style="{style}">{_inline_fmt(h.group(2))}</div>')
            i += 1
            continue

        # 구분선
        if _re.match(r'^[-─━]{3,}$', line.strip()):
            result_lines.append(
                '<hr style="border:none;border-top:1px solid rgba(148,163,184,0.25);margin:12px 0;">'
            )
            i += 1
            continue

        # 빈 줄
        if not line.strip():
            result_lines.append('<div style="height:6px;"></div>')
            i += 1
            continue

        # 숫자 리스트
        if _re.match(r'^\d+\.\s+', line):
            ol_items = []
            while i < len(lines) and _re.match(r'^\d+\.\s+', lines[i]):
                item_text = _re.sub(r'^\d+\.\s+', '', lines[i])
                ol_items.append(
                    f'<li style="margin:6px 0;line-height:1.7;">{_inline_fmt(item_text)}</li>'
                )
                i += 1
            result_lines.append(
                '<ol style="margin:8px 0 10px 22px;padding:0;line-height:1.7;">'
                + ''.join(ol_items) + '</ol>'
            )
            continue

        # 불릿 리스트
        if _re.match(r'^[\-\*•]\s+', line):
            ul_items = []
            while i < len(lines) and _re.match(r'^[\-\*•]\s+', lines[i]):
                item_text = _re.sub(r'^[\-\*•]\s+', '', lines[i])
                ul_items.append(
                    f'<li style="margin:6px 0;line-height:1.7;">{_inline_fmt(item_text)}</li>'
                )
                i += 1
            result_lines.append(
                '<ul style="margin:8px 0 10px 22px;padding:0;line-height:1.7;">'
                + ''.join(ul_items) + '</ul>'
            )
            continue

        # 결론/추천 강조 박스 — 키워드 포함 일반 텍스트
        formatted = _inline_fmt(line)
        if any(kw in line for kw in _CONCLUSION_KW):
            result_lines.append(
                '<div style="'
                'background:rgba(16,185,129,0.1);'
                'border-left:3px solid rgba(16,185,129,0.7);'
                'border-radius:0 6px 6px 0;'
                'padding:7px 12px;margin:6px 0;'
                'font-weight:600;line-height:1.7;'
                f'">{formatted}</div>'
            )
        else:
            result_lines.append(formatted + '<br>')
        i += 1

    return '\n'.join(result_lines)


def _inline_fmt(text: str) -> str:
    """
    인라인 마크다운 변환.
    **bold** → <strong> (색상 inherit, 다크/라이트 자동)
    *italic* → <em>
    `code` → <code>
    잔여 ** 특수문자 완전 제거
    """
    import re as _re
    # **굵게** → <strong>
    text = _re.sub(
        r'\*\*([^*\n]+)\*\*',
        r'<strong style="font-weight:700;">\1</strong>',
        text
    )
    # 짝이 맞지 않는 잔여 ** 제거
    text = text.replace('**', '')
    # *기울임*
    text = _re.sub(r'\*([^*\n]+)\*', r'<em>\1</em>', text)
    # `코드`
    text = _re.sub(
        r'`([^`]+)`',
        r'<code style="background:rgba(99,102,241,0.1);padding:1px 5px;'
        r'border-radius:3px;font-size:0.9em;">\1</code>',
        text
    )
    return text


def _inline_format(text: str) -> str:
    """하위 호환 alias"""
    return _inline_fmt(text)


def format_answer_display(content: str, has_table: bool = False) -> tuple:
    """
    답변 포맷팅.
    표를 HTML로 변환한 뒤 마크다운 전체를 HTML로 변환.
    반환: (html_string, None)  — 두 번째 값은 하위 호환용 None
    """
    _, content_with_tables = extract_table_from_text(content)
    formatted_body = md_to_html_answer(content_with_tables.strip())
    return formatted_body, None

def make_conversation_title(query: str) -> str:
    """첫 질문을 대화 제목으로 변환 (최대 18자 + 말줄임)"""
    title = query.strip().replace("\n", " ")
    return title[:18] + "…" if len(title) > 18 else title


def process_user_query(query):
    import time as _time
    curr_conv = st.session_state.conversations[st.session_state.current_id]

    # [중복 방지]
    if curr_conv["messages"] and curr_conv["messages"][-1].get("content") == query:
        return

    # [생성 중 보호]
    if st.session_state.is_generating:
        st.session_state.queued_query = query
        st.toast("⏳ 이전 답변 생성 중입니다. 완료 후 자동으로 처리됩니다.", icon="⏳")
        return

    # 1. 첫 질문이면 대화 제목 자동 설정
    user_msgs = [m for m in curr_conv["messages"] if m["role"] == "user"]
    if len(user_msgs) == 0:
        curr_conv["title"] = make_conversation_title(query)

    # 2. 사용자 질문 추가
    curr_conv["messages"].append({
        "role": "user",
        "content": query,
        "timestamp": datetime.now().isoformat()
    })
    st.session_state.last_query = query

    # 3. 생성 시작 플래그 ON
    st.session_state.is_generating = True

    # ── (3) Skeleton 플레이스홀더 ────────────────────────────────────
    skeleton_slot = st.empty()
    skeleton_slot.markdown("""
<style>
@keyframes skeleton-wave {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}
.skel-wrap {
    padding: 14px 18px;
    border-radius: 12px;
    background: var(--secondary-background-color);
    margin-bottom: 8px;
    max-width: 82%;
}
.skel-bar {
    height: 13px;
    border-radius: 6px;
    margin-bottom: 10px;
    background: linear-gradient(
        90deg,
        rgba(128,128,128,0.10) 25%,
        rgba(128,128,128,0.22) 50%,
        rgba(128,128,128,0.10) 75%
    );
    background-size: 800px 100%;
    animation: skeleton-wave 1.4s ease-in-out infinite;
}
</style>
<div class="skel-wrap">
  <div class="skel-bar" style="width:88%;"></div>
  <div class="skel-bar" style="width:72%;"></div>
  <div class="skel-bar" style="width:80%;"></div>
  <div class="skel-bar" style="width:55%;margin-bottom:0;"></div>
</div>
""", unsafe_allow_html=True)

    try:
        # 4. 답변 생성 (백그라운드)
        response    = get_rag_response(query, context=curr_conv.get("context", []), team=st.session_state.get("selected_team", ""))
        answer_text = response.get('answer', "").strip()

        # 빈 답변 방어 처리 — LLM이 빈 문자열 반환 시 안내 메시지로 대체
        if not answer_text:
            answer_text = "죄송합니다. 답변 생성 중 문제가 발생했습니다. 같은 질문을 다시 시도하거나, 질문을 조금 다르게 표현해 주세요."

        # Skeleton 제거
        skeleton_slot.empty()

        # ── (2) 스트리밍 효과 ─────────────────────────────────────────
        stream_slot = st.empty()
        displayed   = ""
        # 글자 단위 출력 (마크다운 렌더링을 위해 chunk 단위로 업데이트)
        CHUNK = 3          # 한 번에 출력할 글자 수 (속도 조절)
        DELAY = 0.012      # 초 단위 딜레이
        body_html_stream, _ = format_answer_display("", False)  # 빈 껍데기 확인용

        for i in range(0, len(answer_text), CHUNK):
            displayed = answer_text[: i + CHUNK]
            _body, _ = format_answer_display(displayed, False)
            stream_slot.markdown(
                f'<div class="chat-bubble assistant">{_body}</div>',
                unsafe_allow_html=True
            )
            _time.sleep(DELAY)

        # 최종 완성본으로 교체
        stream_slot.empty()

        # 5. 메시지 저장 (rerun 전에 반드시 완료)
        curr_conv["messages"].append({
            "role"      : "assistant",
            "content"   : answer_text,
            "sources"   : response.get('sources', []),
            "timestamp" : datetime.now().isoformat(),
            "has_table" : response.get('has_table', False),
            "answer_id" : response.get('answer_id', ""),
        })

        # 6. 대화 컨텍스트 누적 (최대 10턴)
        MAX_CONTEXT_TURNS = 10
        if "context" not in curr_conv:
            curr_conv["context"] = []
        curr_conv["context"].append({
            "query"    : query,
            "answer"   : answer_text,
            "timestamp": datetime.now().isoformat()
        })
        if len(curr_conv["context"]) > MAX_CONTEXT_TURNS:
            curr_conv["context"] = curr_conv["context"][-MAX_CONTEXT_TURNS:]

    finally:
        skeleton_slot.empty()
        st.session_state.is_generating = False

    # 7. 대기 중인 질문 처리
    if st.session_state.queued_query:
        st.session_state.pending_query = st.session_state.queued_query
        st.session_state.queued_query  = None

    st.rerun()

# --- 사이드바 ---
with st.sidebar:
    # 생성 중 상태 배너
    if st.session_state.is_generating:
        st.markdown(
            '<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;'
            'padding:10px 14px;margin-bottom:10px;font-size:13px;color:#92400e;">'
            '⏳ <strong>답변 생성 중...</strong><br>'
            '<span style="font-size:11px;">채팅 화면에서 진행 상황을 확인하세요</span>'
            '</div>',
            unsafe_allow_html=True
        )

    # 1. 부서 선택 탭 (최상단 고정)
    st.markdown(
        '<div style="font-size:17px;font-weight:700;color:var(--text-color);margin:4px 0 2px 0;line-height:1.4;">🏢 부서 모드 선택</div>'
        '<hr style="height:3px;border:none;border-radius:2px;background:linear-gradient(90deg,#ff6b6b,#ffa500,#ffd700,#7ed957,#4fc3f7,#7c4dff);margin:3px 0 12px 0;">',
        unsafe_allow_html=True
    )

    team_options = {"국내영업팀": "🚚", "해외영업팀": "🚢", "트랙영업팀": "🚜"}
    TEAM_SHORT   = {"국내영업팀": "국내", "해외영업팀": "해외", "트랙영업팀": "트랙"}

    generating = st.session_state.is_generating   # 짧은 alias
    team_cols = st.columns(3)
    for idx, (t_name, t_icon) in enumerate(team_options.items()):
        is_selected = (st.session_state.selected_team == t_name)
        # 생성 중이면 버튼 비활성화
        btn_clicked = team_cols[idx].button(
            f"{t_icon} {TEAM_SHORT[t_name]}",
            key=f"sidebar_team_{t_name}",
            use_container_width=True,
            type="primary" if is_selected else "secondary",
            disabled=generating
        )
        if btn_clicked and not generating:
            if st.session_state.selected_team != t_name:
                # 현재 팀 상태 저장
                cur = st.session_state.selected_team
                st.session_state.team_conversations[cur] = st.session_state.conversations
                st.session_state.team_current_id[cur] = st.session_state.current_id
                # 새 팀 세션으로 전환
                st.session_state.selected_team = t_name
                st.session_state.conversations = st.session_state.team_conversations[t_name]
                st.session_state.current_id = st.session_state.team_current_id[t_name]
                st.session_state.editing_id = None
                st.session_state.show_suggestions = True
            st.rerun()

    st.markdown(f"**현재 모드:** `{st.session_state.selected_team}`")

    st.markdown(
        '<div style="font-size:17px;font-weight:700;color:var(--text-color);margin:4px 0 2px 0;line-height:1.4;">💬 대화 목록</div>'
        '<hr style="height:3px;border:none;border-radius:2px;background:linear-gradient(90deg,#ff6b6b,#ffa500,#ffd700,#7ed957,#4fc3f7,#7c4dff);margin:3px 0 12px 0;">',
        unsafe_allow_html=True
    )
    
    if st.button("새 대화 시작", use_container_width=True, disabled=generating):
        cur_team = st.session_state.selected_team
        greet_map = {
            "국내영업팀": "안녕하세요! 🚚 국내영업팀 전용 DRB 물류 AI입니다. 무엇을 도와드릴까요?",
            "해외영업팀": "안녕하세요! 🚢 해외영업팀 전용 DRB 물류 AI입니다. 무엇을 도와드릴까요?",
            "트랙영업팀": "안녕하세요! 🚜 트랙영업팀 전용 DRB 물류 AI입니다. 무엇을 도와드릴까요?",
        }
        new_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_conv = {
            "title": "새 대화",
            "messages": [{
                "role": "assistant",
                "content": greet_map.get(cur_team, "안녕하세요! DRB 물류 AI입니다."),
                "timestamp": datetime.now().isoformat(),
                "has_table": False
            }],
            "context": []
        }
        st.session_state.conversations[new_id] = new_conv
        st.session_state.team_conversations[cur_team][new_id] = new_conv
        st.session_state.current_id = new_id
        st.session_state.team_current_id[cur_team] = new_id
        st.session_state.editing_id = None
        st.session_state.show_suggestions = True
        st.rerun()
        st.markdown("---")
        
    # 대화 목록
    for cid in list(st.session_state.conversations.keys()):
        data = st.session_state.conversations[cid]
        is_active = (cid == st.session_state.current_id)
        
        if st.button(
            f"{'🔵' if is_active else '⚪'} {data['title']}",
            key=f"nav_{cid}",
            use_container_width=True,
            disabled=generating
        ):
            st.session_state.current_id = cid
            st.session_state.editing_id = None
            st.rerun()
        
        if is_active:
            col_edit, col_del = st.columns(2)
            with col_edit:
                if st.button("✏️", key=f"edit_{cid}", use_container_width=True, disabled=generating):
                    st.session_state.editing_id = cid
            with col_del:
                if st.button("🗑️", key=f"del_{cid}", use_container_width=True, disabled=generating):
                    if len(st.session_state.conversations) > 1:
                        del st.session_state.conversations[cid]
                        st.session_state.current_id = list(st.session_state.conversations.keys())[0]
                        st.toast("대화가 삭제되었습니다.")
                        st.rerun()
                    else:
                        st.warning("마지막 대화는 삭제할 수 없습니다.")

            if st.session_state.editing_id == cid:
                new_title = st.text_input("새 제목 입력:", value=data['title'], key=f"input_{cid}")
                if st.button("확인", key=f"confirm_{cid}"):
                    st.session_state.conversations[cid]['title'] = new_title
                    st.session_state.editing_id = None
                    st.rerun()
                    
    # ── 포장량 DB 로드 (하드코딩 완전 제거) ─────────────────────────────
    @st.cache_data(ttl=300)
    def load_packing_db():
        """
        '포장량 산출 데이터' 시트 → {포장재키: {자재그룹: 중량kg}} 딕셔너리 반환
        예) {"제품-650박스": {"B01": 27.7, "B02": 25.0, "N18": 25.0, "N19": 31.0}, ...}
        """
        import glob as _glob, re as _re

        import os as _os
        _env_path = _os.environ.get("LOGIBOT_EXCEL_PATH", "")
        search_paths = (
            ([_env_path] if _env_path and _glob.glob(_env_path) else []) +
            _glob.glob("rag_pipeline/data/source_docs/*V5*.xlsx") +
            _glob.glob("rag_pipeline/data/source_docs/*V4*.xlsx") +
            _glob.glob("rag_pipeline/data/source_docs/*V3*.xlsx") +
            _glob.glob("rag_pipeline/data/source_docs/*.xlsx")
        )

        df = None
        for path in search_paths:
            try:
                xf = pd.ExcelFile(path)
                sheet = next((s for s in xf.sheet_names if "포장량 산출 데이터" in s), None)
                if sheet:
                    df = pd.read_excel(path, sheet_name=sheet, header=None).fillna("")
                    break
            except Exception:
                continue

        if df is None:
            return {}, [], []

        # 헤더 행(index=2)에서 자재그룹 컬럼 위치 탐지
        header_row = df.iloc[2].tolist()
        group_cols = {}
        for ci, cell in enumerate(header_row):
            m = _re.search(r'\b(B01|B02|N18|N19)\b', str(cell))
            if m:
                group_cols[m.group(1)] = ci

        # 포장재 행 설명 → 키 매핑 (순서 중요: 1090 → 650 순으로 체크)
        PACKING_KEY_MAP = [
            (r'제품.*?1090',   "제품-1090박스"),
            (r'제품.*?650',    "제품-650박스"),
            (r'제품.*?세미',   "제품-세미박스"),
            (r'제품.*?마대',   "제품-마대"),
            (r'제품.*?600',    "제품-600박스"),
            (r'슬리브.*?650',  "슬리브-650박스"),
            (r'슬리브.*?세미', "슬리브-세미박스"),
            (r'슬리브.*?600',  "슬리브-600박스"),
        ]

        packing_table = {}
        for row_idx in range(3, len(df)):
            desc = str(df.iloc[row_idx, 1])
            if not desc.strip():
                continue
            for pattern, key in PACKING_KEY_MAP:
                if _re.search(pattern, desc):
                    grp_weights = {}
                    for grp, ci in group_cols.items():
                        cell = str(df.iloc[row_idx, ci])
                        m = _re.search(r'(\d+\.?\d*)\s*$', cell.strip())
                        if m:
                            grp_weights[grp] = float(m.group(1))
                    if grp_weights:
                        packing_table[key] = grp_weights
                    break

        group_list   = list(group_cols.keys())
        packing_list = list(packing_table.keys())
        return packing_table, group_list, packing_list

    PACKING_TABLE, GROUP_LIST, PACKING_LIST = load_packing_db()

    # ── 포장재별 규격 정의 (요구사항 기반) ───────────────────────────────────
    # boxes_per_plt : PLT당 박스 수
    # plt_w/l/h     : 파렛트 단위 치수 (m) - 1단 기준
    # pkg_w/l/h     : 패키징 단위 치수 (m) - 2단 적재 기준 (없으면 1단과 동일)
    # has_pkg       : 패키징(2단) 단위 표현 여부
    # layers        : 3D 시각화 적재 단수
    PACKING_SPEC = {
        "제품-600박스": {
            "boxes_per_plt": 8,
            "plt_w": 1.2, "plt_l": 0.8, "plt_h": 0.73,
            "pkg_w": 1.2, "pkg_l": 0.8, "pkg_h": 1.46,
            "has_pkg": True, "layers": 2,
        },
        "제품-650박스": {
            "boxes_per_plt": 20,
            "plt_w": 1.1, "plt_l": 1.1, "plt_h": 2.20,
            "pkg_w": 1.1, "pkg_l": 1.1, "pkg_h": 2.20,
            "has_pkg": False, "layers": 1,
        },
        "제품-1090박스": {
            "boxes_per_plt": 4,
            "plt_w": 1.1, "plt_l": 1.1, "plt_h": 1.11,
            "pkg_w": 1.1, "pkg_l": 1.1, "pkg_h": 2.22,
            "has_pkg": True, "layers": 2,
        },
        "제품-세미박스": {
            "boxes_per_plt": 1,
            "plt_w": 1.1, "plt_l": 1.15, "plt_h": 1.10,
            "pkg_w": 1.1, "pkg_l": 1.15, "pkg_h": 1.10,
            "has_pkg": False, "layers": 1,
        },
        "제품-마대": {
            "boxes_per_plt": 20,
            "plt_w": 1.1, "plt_l": 1.1, "plt_h": 1.20,
            "pkg_w": 1.1, "pkg_l": 1.1, "pkg_h": 1.20,
            "has_pkg": False, "layers": 1,
        },
    }
    # 슬리브는 제품과 동일 규격 기본 적용
    for k in ["슬리브-650박스","슬리브-세미박스","슬리브-600박스"]:
        base = k.replace("슬리브-", "제품-")
        if base in PACKING_SPEC:
            PACKING_SPEC[k] = PACKING_SPEC[base].copy()

    def _get_packing_spec(packing_name: str) -> dict:
        return PACKING_SPEC.get(packing_name, {
            "boxes_per_plt": 20, "plt_w": 1.1, "plt_l": 1.1, "plt_h": 2.20,
            "pkg_w": 1.1, "pkg_l": 1.1, "pkg_h": 2.20,
            "has_pkg": False, "layers": 1,
        })

    # PLT당 박스 수 (포장재 선택 전 기본값 — 실제 계산에서는 PACKING_SPEC 우선)
    GROUP_PALLET_LIMIT = {"B01": 20, "B02": 20, "N18": 20, "N19": 20}

    current_team = st.session_state.selected_team

    if current_team == "해외영업팀":
        st.markdown(
            '<div style="font-size:17px;font-weight:700;color:var(--text-color);margin:4px 0 2px 0;line-height:1.4;">📦 수출 포장량 시뮬레이터</div>'
            '<hr style="height:3px;border:none;border-radius:2px;background:linear-gradient(90deg,#ff6b6b,#ffa500,#ffd700,#7ed957,#4fc3f7,#7c4dff);margin:3px 0 12px 0;">',
            unsafe_allow_html=True
        )

        with st.container(border=True):
            total_target_weight = st.number_input(
                "목표 총 중량 (kg)", min_value=0.0, value=800.0, step=10.0,
                on_change=lambda: st.session_state.update({"export_sim_run": False})
            )
            selected_packing = st.selectbox(
                "포장재 종류",
                options=["선택하세요"] + (PACKING_LIST or [
                    "제품-650박스","제품-1090박스","제품-세미박스",
                    "제품-마대","제품-600박스",
                    "슬리브-650박스","슬리브-세미박스","슬리브-600박스"
                ]),
                on_change=lambda: st.session_state.update({"export_sim_run": False})
            )
            # ── 복수 자재그룹 선택 (multiselect) ──────────────────────────
            selected_groups = st.multiselect(
                "자재그룹 (복수 선택 가능)",
                options=GROUP_LIST or ["B01","B02","N18","N19"],
                placeholder="자재그룹을 선택하세요 (여러 개 선택 가능)",
                on_change=lambda: st.session_state.update({"export_sim_run": False})
            )

            # 복수 선택 시 그룹별 중량 비율 입력
            group_weights = {}   # {그룹명: 해당 그룹 중량(kg)}
            if len(selected_groups) > 1:
                st.markdown("**그룹별 중량 배분** (총합이 목표 중량과 같아야 합니다)")
                ratio_cols = st.columns(len(selected_groups))
                remaining = total_target_weight
                for i, grp in enumerate(selected_groups):
                    with ratio_cols[i]:
                        if i < len(selected_groups) - 1:
                            default_val = round(total_target_weight / len(selected_groups), 1)
                            w = st.number_input(
                                f"{grp} (kg)",
                                min_value=0.0,
                                max_value=float(total_target_weight),
                                value=min(default_val, remaining),
                                step=10.0,
                                key=f"grp_weight_{grp}"
                            )
                            group_weights[grp] = w
                            remaining -= w
                        else:
                            # 마지막 그룹은 나머지 자동 계산
                            last_val = max(0.0, round(remaining, 1))
                            st.markdown(
                                f'<div style="margin-top:4px;">'
                                f'<label style="font-size:12px;color:var(--text-color);'
                                f'opacity:0.7;">{grp} (kg)</label>'
                                f'<div style="background:var(--secondary-background-color);'
                                f'border:1px solid rgba(128,128,128,0.25);border-radius:6px;'
                                f'padding:8px 10px;font-size:14px;font-weight:600;'
                                f'color:var(--text-color);margin-top:4px;word-break:break-all;">'
                                f'{last_val:,.1f}</div></div>',
                                unsafe_allow_html=True
                            )
                            group_weights[grp] = last_val

                # 합계 검증
                total_assigned = sum(group_weights.values())
                diff = abs(total_assigned - total_target_weight)
                if diff > 0.5:
                    st.warning(
                        f"⚠️ 배분 합계 {total_assigned:,.1f}kg ≠ 목표 {total_target_weight:,.1f}kg "
                        f"(차이: {diff:,.1f}kg)"
                    )
            elif len(selected_groups) == 1:
                group_weights[selected_groups[0]] = total_target_weight

        # ── 조회 버튼 ────────────────────────────────────────────────────
        if "export_sim_run" not in st.session_state:
            st.session_state.export_sim_run = False

        if st.button("🔍 포장량 계산", use_container_width=True, key="export_run_btn"):
            st.session_state.export_sim_run = True
            record_simulator_count("수출포장량", team=st.session_state.get("selected_team", ""))

        # ── 계산 시작 ────────────────────────────────────────────────────
        if not (selected_groups and selected_packing != "선택하세요"):
            if not selected_groups:
                st.info("자재그룹과 포장재 종류를 선택 후 **포장량 계산** 버튼을 눌러주세요.")
            elif selected_packing == "선택하세요":
                st.info("포장재 종류를 선택 후 **포장량 계산** 버튼을 눌러주세요.")
        elif not st.session_state.export_sim_run:
            st.info("⬆️ 수치를 입력 후 **포장량 계산** 버튼을 눌러주세요.")
        else:

            st.markdown('<div style="font-size:14px;font-weight:600;color:var(--text-color);margin:10px 0 6px 0;opacity:0.9;">📊 시뮬레이션 결과</div>', unsafe_allow_html=True)

            # 슬리브 안내
            if "슬리브" in selected_packing:
                st.info("ℹ️ 슬리브 항목은 현재 파렛트 포장으로 변경 중인 항목입니다.")

            # ── 포장재 규격 로드 ─────────────────────────────────────────
            import math as _math
            _pspec       = _get_packing_spec(selected_packing)
            _boxes_pp    = _pspec["boxes_per_plt"]   # PLT당 박스 수
            _has_pkg     = _pspec["has_pkg"]          # 패키징(2단) 표현 여부
            _layers      = _pspec["layers"]
            _plt_w       = _pspec["plt_w"]
            _plt_l       = _pspec["plt_l"]
            _plt_h       = _pspec["plt_h"]
            _pkg_h       = _pspec["pkg_h"]
            _pkg_unit_txt = (
                f"{int(_pspec['pkg_w']*1000)}×{int(_pspec['pkg_l']*1000)}×{int(_pkg_h*1000)}mm"
                if _has_pkg else ""
            )
            _plt_unit_txt = f"{int(_plt_w*1000)}×{int(_plt_l*1000)}×{int(_plt_h*1000)}mm"

            # ── 그룹별 개별 결과 테이블 ─────────────────────────────────
            if len(selected_groups) > 1:
                st.markdown("**그룹별 계산**")
                rows = []
                total_boxes   = 0.0
                total_pallets = 0.0
                for grp in selected_groups:
                    gw     = group_weights.get(grp, 0.0)
                    unit_w = (PACKING_TABLE.get(selected_packing, {}).get(grp)
                              or PACKING_TABLE.get(selected_packing, {}).get(
                                  list(PACKING_TABLE.get(selected_packing, {}).keys())[0]
                                  if PACKING_TABLE.get(selected_packing) else None))
                    if not unit_w:
                        st.warning(f"⚠️ {grp} × {selected_packing} 조합의 중량 데이터가 없습니다.")
                        continue
                    g_boxes   = _math.ceil(gw / unit_w)
                    g_pallets = _math.ceil(g_boxes / _boxes_pp)
                    total_boxes   += g_boxes
                    total_pallets += g_pallets
                    rows.append({
                        "그룹": grp,
                        "중량(kg)": f"{gw:,.1f}",
                        "박스당kg": f"{unit_w}",
                        "박스(PKG)": f"{g_boxes}",
                        "PLT": f"{g_pallets}",
                        "PLT당": f"{_boxes_pp}",
                    })
                rows.append({
                    "그룹": "합계",
                    "중량(kg)": f"{sum(group_weights.values()):,.1f}",
                    "박스당kg": "",
                    "박스(PKG)": f"{int(total_boxes)}",
                    "PLT": f"{int(total_pallets)}",
                    "PLT당": "",
                })
                # HTML 테이블 렌더링
                _cols = list(rows[0].keys())
                _widths = {"그룹":"9%","중량(kg)":"18%","박스당kg":"12%","박스(PKG)":"14%","PLT":"9%","PLT당":"9%"}
                _thead = "".join(
                    '<th style="background:rgba(59,130,246,0.15);padding:6px 8px;'
                    'font-size:11px;font-weight:700;color:var(--text-color);'
                    f'white-space:nowrap;width:{_widths.get(h,"auto")};">{h}</th>'
                    for h in _cols
                )
                _tbody = ""
                for ri, row in enumerate(rows):
                    _is_tot = row["그룹"] == "합계"
                    _bg = "rgba(59,130,246,0.07)" if _is_tot else ("rgba(128,128,128,0.04)" if ri%2==0 else "transparent")
                    _fw = "700" if _is_tot else "400"
                    _tbody += f"<tr style='background:{_bg};'>"
                    for h in _cols:
                        v = row.get(h, "")
                        _tbody += (
                            f'<td style="padding:6px 8px;font-size:12px;color:var(--text-color);'
                            f'font-weight:{_fw};white-space:nowrap;" title="{v}">{v}</td>'
                        )
                    _tbody += "</tr>"
                st.markdown(
                    '<div style="overflow-x:auto;border-radius:8px;'
                    'border:1px solid rgba(128,128,128,0.2);margin:4px 0 8px;">'
                    '<table style="width:100%;border-collapse:collapse;">'
                    f'<thead><tr>{_thead}</tr></thead>'
                    f'<tbody>{_tbody}</tbody>'
                    '</table></div>',
                    unsafe_allow_html=True
                )
                calc_boxes   = total_boxes
                calc_pallets = total_pallets

            else:
                # 단일 그룹
                grp    = selected_groups[0]
                unit_w = PACKING_TABLE.get(selected_packing, {}).get(grp)
                if not unit_w:
                    st.warning(f"⚠️ {grp} × {selected_packing} 조합의 중량 데이터가 없습니다.")
                    unit_w = 1
                calc_boxes   = _math.ceil(total_target_weight / unit_w)
                calc_pallets = _math.ceil(calc_boxes / _boxes_pp)

                _c1, _c2 = st.columns(2)
                with _c1:
                    st.metric("필요 박스", f"{calc_boxes} PKG")
                with _c2:
                    st.metric("필요 PLT", f"{calc_pallets} PLT")
                st.caption(
                    f"ℹ️ {grp} × {selected_packing} = {unit_w}kg/박스 / PLT당 {_boxes_pp}박스"
                )

            # ── 파렛트 규격 안내 ─────────────────────────────────────────
            _spec_lines = [f"📦 파렛트 단위: {_plt_unit_txt} / PLT당 {_boxes_pp}박스"]
            if _has_pkg:
                _spec_lines.append(f"📦 패키징 단위: {_pkg_unit_txt} ({_layers}단 적재)")
            st.caption(" · ".join(_spec_lines))

            # ── 합산 요약 (복수 그룹일 때만) ─────────────────────────────
            if len(selected_groups) > 1:
                st.markdown(f"""
<div style="display:flex;gap:8px;margin:10px 0 4px;">
  <div style="flex:1;background:var(--secondary-background-color);border-radius:10px;
              padding:10px 14px;border:1.5px solid rgba(128,128,128,0.15);">
    <div style="font-size:11px;opacity:0.6;color:var(--text-color);margin-bottom:4px;">총 박스</div>
    <div style="font-size:18px;font-weight:700;color:var(--text-color);">{int(calc_boxes)} PKG</div>
  </div>
  <div style="flex:1;background:var(--secondary-background-color);border-radius:10px;
              padding:10px 14px;border:1.5px solid rgba(128,128,128,0.15);">
    <div style="font-size:11px;opacity:0.6;color:var(--text-color);margin-bottom:4px;">총 PLT</div>
    <div style="font-size:18px;font-weight:700;color:var(--text-color);">{int(calc_pallets)} PLT</div>
  </div>
  <div style="flex:1;background:var(--secondary-background-color);border-radius:10px;
              padding:10px 14px;border:1.5px solid rgba(128,128,128,0.15);overflow:hidden;">
    <div style="font-size:11px;opacity:0.6;color:var(--text-color);margin-bottom:4px;">포장재</div>
    <div style="font-size:13px;font-weight:700;color:var(--text-color);
                white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
         title="{selected_packing}">{selected_packing}</div>
  </div>
</div>
""", unsafe_allow_html=True)

            # ── 배차 및 컨테이너 분석 ─────────────────────────────────────
            best_truck = get_db_transport_advice(calc_pallets)

            with st.expander("🚚 배차 및 컨테이너 분석", expanded=True):
                if best_truck:
                    st.success(f"**추천 차량:** {best_truck['name']}")
                    st.write(f"📏 **적재함 제원:** {best_truck['spec']}")
                    st.write(f"📦 **최대 적재 가능:** {best_truck['max_plt']} PLT")

                    # 컨테이너 기준: 20ft(10 PLT), 40ft(20 PLT)
                    if calc_pallets <= 10:
                        cntr_type, max_cntr_plt = "20ft", 10
                    else:
                        cntr_type, max_cntr_plt = "40ft", 20

                    cntr_count = int(
                        (calc_pallets // max_cntr_plt) +
                        (1 if calc_pallets % max_cntr_plt > 0 else 0)
                    )
                    st.info(f"🚢 **해외 운송: {cntr_type} 컨테이너 {cntr_count}대 예상**")

                    # 남은 공간
                    used_last = calc_pallets % max_cntr_plt
                    if used_last == 0 and calc_pallets > 0:
                        used_last = max_cntr_plt
                    rem_plt = max_cntr_plt - used_last

                    if rem_plt > 0:
                        st.markdown(f"**💡 풀 컨테이너(FCL)를 위한 추가 가능량** (남은 공간: {rem_plt:.2f} PLT)")
                        add_cols = st.columns(2)
                        for idx, g_code in enumerate(["B01", "B02", "N18", "N19"]):
                            with add_cols[idx % 2]:
                                if g_code in GROUP_PALLET_LIMIT:
                                    add_boxes = int(rem_plt * GROUP_PALLET_LIMIT[g_code])
                                    st.write(f"**{g_code}** : {add_boxes}박스")
                                else:
                                    st.write(f"**{g_code}** : 정보 없음")
                    else:
                        st.success("✅ 현재 풀 컨테이너 상태입니다.")
                else:
                    st.warning("⚠️ 대량 물량으로 인한 별도 배차 협의가 필요합니다.")

            # ── 챗봇 연동 버튼 ────────────────────────────────────────────
            _3d_spec   = _get_packing_spec(selected_packing)
            _cntr_type = "20ft" if int(calc_pallets) <= 10 else "40ft"
            _max_cap   = 10 if _cntr_type == "20ft" else 20
            _box_type  = selected_packing.replace("제품-","").replace("슬리브-","")
            _3d_plt_h  = _3d_spec["pkg_h"] if _3d_spec["has_pkg"] else _3d_spec["plt_h"]
            _3d_layers = _3d_spec["layers"]
            _grp       = selected_groups[0] if selected_groups else "B01"

            # 컨테이너 대수별 PLT 배분 계산
            _total_plt_int = int(calc_pallets)
            _cntr_list = []   # [(컨테이너번호, 적재PLT)]
            _remaining = _total_plt_int
            _cntr_idx  = 1
            while _remaining > 0:
                _this_plt = min(_remaining, _max_cap)
                _cntr_list.append((_cntr_idx, _this_plt))
                _remaining -= _this_plt
                _cntr_idx  += 1

            # 3D 버튼: 컨테이너 1대면 기존 방식, 2대 이상이면 각각 버튼
            if len(_cntr_list) == 1:
                _btn3d_cntr, _btnq_cntr = st.columns([1, 1])
                with _btn3d_cntr:
                    if st.button("🧊 3D 입체 보기", use_container_width=True, key="cntr_3d_btn"):
                        _used_plt = _cntr_list[0][1]
                        show_3d_view_popup(
                            trucks=[{
                                "name": f"{_cntr_type} 컨테이너",
                                "spec": f"컨테이너 {_cntr_type}",
                                "assigned_plt"  : _used_plt,
                                "max_plt_cap"   : _max_cap,
                                "boxes_per_plt" : _3d_spec["boxes_per_plt"],
                                "box_layers"    : _3d_layers,
                                "box_type"      : _box_type,
                                "container_type": _cntr_type,
                                "plt_h_override": _3d_plt_h,
                                "has_pkg"       : _3d_spec["has_pkg"],
                                "is_lowbed"     : False,
                            }],
                            resolved_items=[{
                                "name": _grp, "code": _grp,
                                "plt_w": _3d_spec["plt_w"], "plt_l": _3d_spec["plt_l"],
                                "pallets": _used_plt,
                            }],
                            mode="container"
                        )
                with _btnq_cntr:
                    if st.button("📋 시뮬레이터 문의하기", use_container_width=True, key="cntr_query_btn"):
                        grp_summary = ", ".join(f"{g}({group_weights.get(g,0):,.0f}kg)" for g in selected_groups)
                        sim_summary = (
                            f"포장재: {selected_packing}\n"
                            f"자재그룹: {grp_summary}\n"
                            f"목표 중량: {total_target_weight:,.0f}kg\n"
                            f"계산 결과: {int(calc_boxes)}박스 / {int(calc_pallets)}PLT"
                        )
                        record_sim_inquiry("수출포장량", team=st.session_state.get("selected_team", ""))
                        show_simulator_inquiry_popup("수출 포장량 시뮬레이터", sim_summary)
            else:
                # 컨테이너 2대 이상: 각 컨테이너별 3D 버튼 행
                st.markdown(
                    f'<div style="font-size:12px;font-weight:600;color:var(--text-color);'
                    f'opacity:0.7;margin:6px 0 4px;">🚢 컨테이너 {len(_cntr_list)}대 — 각각 3D로 확인하세요</div>',
                    unsafe_allow_html=True
                )
                _3d_cols = st.columns(len(_cntr_list))
                for _ci, (_cno, _cplt) in enumerate(_cntr_list):
                    with _3d_cols[_ci]:
                        _is_full = (_cplt == _max_cap)
                        _label = f"🧊 {_cno}번 컨테이너\n({'풀' if _is_full else f'{_cplt}/{_max_cap} PLT'})"
                        if st.button(_label, use_container_width=True, key=f"cntr_3d_btn_{_cno}"):
                            show_3d_view_popup(
                                trucks=[{
                                    "name"          : f"{_cntr_type} {_cno}번 컨테이너",
                                    "spec"          : f"컨테이너 {_cntr_type}",
                                    "assigned_plt"  : _cplt,
                                    "max_plt_cap"   : _max_cap,
                                    "boxes_per_plt" : _3d_spec["boxes_per_plt"],
                                    "box_layers"    : _3d_layers,
                                    "box_type"      : _box_type,
                                    "container_type": _cntr_type,
                                    "plt_h_override": _3d_plt_h,
                                    "has_pkg"       : _3d_spec["has_pkg"],
                                    "is_lowbed"     : False,
                                }],
                                resolved_items=[{
                                    "name": _grp, "code": _grp,
                                    "plt_w": _3d_spec["plt_w"], "plt_l": _3d_spec["plt_l"],
                                    "pallets": _cplt,
                                }],
                                mode="container"
                            )
                # 문의 버튼은 별도 행
                if st.button("📋 시뮬레이터 문의하기", use_container_width=True, key="cntr_query_btn"):
                    grp_summary = ", ".join(f"{g}({group_weights.get(g,0):,.0f}kg)" for g in selected_groups)
                    sim_summary = (
                        f"포장재: {selected_packing}\n"
                        f"자재그룹: {grp_summary}\n"
                        f"목표 중량: {total_target_weight:,.0f}kg\n"
                        f"계산 결과: {int(calc_boxes)}박스 / {int(calc_pallets)}PLT\n"
                        f"컨테이너: {_cntr_type} {len(_cntr_list)}대"
                    )
                    record_sim_inquiry("수출포장량", team=st.session_state.get("selected_team", ""))
                    show_simulator_inquiry_popup("수출 포장량 시뮬레이터", sim_summary)


    elif current_team == "국내영업팀":
        st.markdown(
            '<div style="font-size:17px;font-weight:700;color:var(--text-color);margin:4px 0 2px 0;line-height:1.4;">🚚 국내 최적 운임 비교</div>'
            '<hr style="height:3px;border:none;border-radius:2px;background:linear-gradient(90deg,#ff6b6b,#ffa500,#ffd700,#7ed957,#4fc3f7,#7c4dff);margin:3px 0 12px 0;">',
            unsafe_allow_html=True
        )

        @st.cache_data(ttl=300)
        def _check_fare_loaded():
            return get_freight_meta().get("loaded", False)

        fare_loaded = _check_fare_loaded()

        if not fare_loaded:
            st.warning("⚠️ 운임 데이터가 Qdrant에 없습니다. data_loader.py로 운임_테이블.xlsx를 재적재해주세요.")
        else:
            with st.container(border=True):
                destination = st.text_input("📍 도착지", placeholder="예: 창원, 광주, 서울, 인천", key="fare_dest")
                weight_kg   = st.number_input("⚖️ 중량 (kg)", min_value=1, value=100, key="fare_weight")
                search_btn  = st.button("🔍 운임 조회", use_container_width=True, key="fare_search_btn")

            if search_btn and not destination:
                st.warning("도착지를 입력해주세요.")

            if search_btn and destination:
                record_simulator_count("국내운임비교", team=st.session_state.get("selected_team", ""))
                with st.spinner("운임 계산 중..."):
                    fare_result = calculate_fare_comparison(destination, weight_kg)

                best  = fare_result.get("추천")
                icon_map  = {"직송": "🚛", "화물": "📦", "택배": "🏍️"}
                color_map = {"직송": "#2563eb", "화물": "#16a34a", "택배": "#f59e0b"}

                st.markdown(f"""
<style>
.fare-hero{{
  border-radius:16px;padding:28px 20px;margin:10px 0;text-align:center;
  background:linear-gradient(135deg,{color_map.get(best,'#64748b')}dd,{color_map.get(best,'#64748b')}88);
}}
.fare-hero-icon{{font-size:52px;line-height:1;margin-bottom:10px;}}
.fare-hero-label{{font-size:11px;color:rgba(255,255,255,0.8);letter-spacing:1px;margin-bottom:4px;}}
.fare-hero-value{{font-size:40px;font-weight:900;color:#fff;line-height:1.2;}}
.fare-hero-sub{{font-size:12px;color:rgba(255,255,255,0.75);margin-top:8px;}}
</style>""", unsafe_allow_html=True)

                if best:
                    direct = fare_result.get("직송")
                    sub_parts = [destination, f"{weight_kg:,}kg"]
                    if direct and direct.get("장거리"):
                        sub_parts.append("장거리 20% 가산 적용")
                    if direct and direct.get("차종"):
                        sub_parts.append(f"차종: {direct['차종']}")
                    st.markdown(f"""
<div class="fare-hero">
  <div class="fare-hero-icon">{icon_map[best]}</div>
  <div class="fare-hero-label">추천 운송 방식</div>
  <div class="fare-hero-value">{best}</div>
  <div class="fare-hero-sub">{' · '.join(sub_parts)}</div>
</div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""
<div class="fare-hero" style="background:linear-gradient(135deg,#64748bdd,#64748b88);">
  <div class="fare-hero-icon">❓</div>
  <div class="fare-hero-label">운임 조회 결과</div>
  <div class="fare-hero-value">데이터 없음</div>
  <div class="fare-hero-sub">{destination} · 도착지를 다시 확인해주세요</div>
</div>""", unsafe_allow_html=True)

                if st.button("📋 시뮬레이터 문의하기", use_container_width=True, key="fare_inquiry_btn"):
                    direct  = fare_result.get("직송")
                    cargo   = fare_result.get("화물")
                    parcel  = fare_result.get("택배")
                    lines   = [
                        f"도착지: {destination} / 중량: {weight_kg:,}kg",
                        f"추천: {best or '없음'}",
                    ]
                    if direct:
                        lines.append(f"직송 - 차종:{direct.get('차종')} / 권역:{direct.get('권역')} / {'장거리20%↑' if direct.get('장거리') else '단거리'}")
                    if cargo:
                        lines.append(f"화물 - 단가:{cargo.get('단가',0):,}원/kg")
                    if parcel:
                        lines.append(f"택배 - 단가:{parcel.get('단가',0):,}원/kg")
                    record_sim_inquiry("국내운임비교", team=st.session_state.get("selected_team", ""))
                    show_simulator_inquiry_popup("국내 최적 운임 비교", "\n".join(lines))


        # ── 국내 최적 배차 시뮬레이터 (국내영업팀 전용) ─────────────────────
        st.markdown(
            '<div style="font-size:17px;font-weight:700;color:var(--text-color);margin:4px 0 2px 0;line-height:1.4;">🚛 최적 배차 시뮬레이터</div>'
            '<hr style="height:3px;border:none;border-radius:2px;background:linear-gradient(90deg,#ff6b6b,#ffa500,#ffd700,#7ed957,#4fc3f7,#7c4dff);margin:3px 0 12px 0;">',
            unsafe_allow_html=True
        )

        # ── 공통 데이터 로드 ────────────────────────────────────────────────
        @st.cache_data(ttl=300)
        def load_crawler_data_dom():
            import glob as _glob, os as _os
            CRAWLER_SHEET_KEYWORD = "크롤러"
            _env_path = _os.environ.get("LOGIBOT_EXCEL_PATH", "")
            search_paths = (
                ([_env_path] if _env_path and _glob.glob(_env_path) else []) +
                _glob.glob("rag_pipeline/data/source_docs/*V5*.xlsx") +
                _glob.glob("rag_pipeline/data/source_docs/*V4*.xlsx") +
                _glob.glob("rag_pipeline/data/source_docs/*V3*.xlsx") +
                _glob.glob("rag_pipeline/data/source_docs/*.xlsx") +
                _glob.glob("/mnt/user-data/uploads/*.xlsx")
            )
            df = None
            for path in search_paths:
                try:
                    xf = pd.ExcelFile(path)
                    crawler_sheet = next(
                        (s for s in xf.sheet_names if CRAWLER_SHEET_KEYWORD in s), None
                    )
                    if not crawler_sheet:
                        continue
                    df_test = pd.read_excel(path, sheet_name=crawler_sheet, header=0, nrows=2)
                    first_col = str(df_test.columns[0])
                    if first_col.startswith("[") or "Unnamed" in first_col:
                        df = pd.read_excel(path, sheet_name=crawler_sheet, header=1).fillna("")
                    else:
                        df = pd.read_excel(path, sheet_name=crawler_sheet, header=0).fillna("")
                    break
                except Exception:
                    continue
            if df is None:
                return {}
            cols = df.columns.tolist()
            def find_col(kw):
                return next((c for c in cols if kw in str(c)), None)
            code_col   = find_col("자재코드")
            name_col   = find_col("자재내역")
            qty_col    = find_col("최대 적재 수량") or find_col("적재 수량")
            size_col   = find_col("사이즈")
            weight_col = find_col("중량") or find_col("KG") or find_col("kg")
            if not code_col:
                return {}
            data = {}
            for _, row in df.iterrows():
                code = str(row.get(code_col, "")).strip().split(".")[0].strip()
                if not code or code in ("nan", ""):
                    continue
                size_raw = str(row.get(size_col, "1000*1100")).strip() if size_col else "1000*1100"
                try:
                    w_mm, l_mm = [float(x) for x in size_raw.replace("×", "*").split("*")]
                except Exception:
                    w_mm, l_mm = 1000.0, 1100.0
                try:
                    max_pc = int(float(str(row.get(qty_col, 1)).strip())) if qty_col else 1
                except Exception:
                    max_pc = 1
                weight_per_pc = None
                if weight_col:
                    try:
                        val = str(row.get(weight_col, "")).strip()
                        if val and val not in ("nan", ""):
                            weight_per_pc = float(val)
                    except Exception:
                        weight_per_pc = None
                data[code] = {
                    "name"         : str(row.get(name_col, "")).strip() if name_col else "",
                    "max_pc"       : max_pc,
                    "plt_w"        : w_mm / 1000,
                    "plt_l"        : l_mm / 1000,
                    "weight_per_pc": weight_per_pc,
                }
            return data

        DOM_CRAWLER_DATA = load_crawler_data_dom()

        # ── 배차 결과 렌더링 헬퍼 ───────────────────────────────────────────
        def _render_dispatch_result(dispatch_result, sim_key_suffix=""):
            """분할·단일 배차 결과를 가독성 높은 카드로 렌더링"""
            import math as _math

            trucks           = dispatch_result.get("trucks", [])
            total_plt        = dispatch_result.get("total_plt", 0)
            total_weight_kg  = dispatch_result.get("total_weight_kg", 0.0)
            is_split         = dispatch_result.get("split", False)
            error            = dispatch_result.get("error")

            if error:
                st.warning(f"⚠️ {error}")
                return

            if not trucks:
                st.warning("⚠️ 적합한 차량이 없습니다. 물류팀에 직접 문의하세요.")
                return

            # ── 공통 CSS (라이트·다크 모두 대응) ──────────────────────────
            st.markdown("""
<style>
.dispatch-card {
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 12px;
    border: 1.5px solid rgba(128,128,128,0.2);
    background: var(--secondary-background-color);
}
.dispatch-card-header {
    font-size: 15px;
    font-weight: 700;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-color);
}
.dispatch-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.3px;
}
.badge-ok   { background: rgba(34,197,94,0.18); color: #16a34a; }
.badge-warn { background: rgba(234,179,8,0.18);  color: #b45309; }
.badge-split{ background: rgba(59,130,246,0.18); color: #1d4ed8; }
.dispatch-row {
    display: flex;
    gap: 8px;
    margin-bottom: 8px;
    flex-wrap: wrap;
}
.dispatch-cell {
    flex: 1;
    min-width: 80px;
    background: rgba(128,128,128,0.08);
    border-radius: 8px;
    padding: 8px 10px;
    text-align: center;
}
.dispatch-cell-label {
    font-size: 11px;
    color: var(--text-color);
    opacity: 0.6;
    margin-bottom: 3px;
    white-space: nowrap;
}
.dispatch-cell-value {
    font-size: 14px;
    font-weight: 700;
    color: var(--text-color);
    word-break: break-word;
}
.dispatch-cell-sub {
    font-size: 11px;
    color: var(--text-color);
    opacity: 0.55;
    margin-top: 1px;
}
.ratio-bar-wrap {
    margin: 6px 0 2px;
    background: rgba(128,128,128,0.12);
    border-radius: 20px;
    height: 8px;
    overflow: hidden;
}
.ratio-bar-fill-ok   { height: 8px; border-radius: 20px; background: linear-gradient(90deg,#22c55e,#4ade80); }
.ratio-bar-fill-warn { height: 8px; border-radius: 20px; background: linear-gradient(90deg,#f59e0b,#fbbf24); }
.ratio-bar-fill-over { height: 8px; border-radius: 20px; background: linear-gradient(90deg,#ef4444,#f87171); }
.dispatch-divider {
    border: none;
    border-top: 1.5px dashed rgba(128,128,128,0.3);
    margin: 14px 0;
}
.dispatch-summary-box {
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 14px;
    background: rgba(59,130,246,0.08);
    border: 1.5px solid rgba(59,130,246,0.2);
    color: var(--text-color);
    font-size: 13px;
}
</style>
""", unsafe_allow_html=True)

            # ── 상단 요약 박스 ─────────────────────────────────────────────
            split_badge = (
                '<span class="dispatch-badge badge-split">🔀 분할 배차</span>'
                if is_split else
                '<span class="dispatch-badge badge-ok">✅ 단일 배차</span>'
            )
            st.markdown(f"""
<div class="dispatch-summary-box">
  <strong>배차 요약</strong> &nbsp;{split_badge}<br>
  <span style="opacity:0.7;">총 파렛트 {total_plt} PLT &nbsp;|&nbsp;
  총 중량 {total_weight_kg:,.0f} kg ({total_weight_kg/1000:.2f} ton) &nbsp;|&nbsp;
  차량 {len(trucks)}대</span>
</div>
""", unsafe_allow_html=True)

            # ── 차량별 카드 ────────────────────────────────────────────────
            for idx, truck in enumerate(trucks, 1):
                if truck.get("is_lowbed"):
                    st.markdown(f"""
<div class="dispatch-card">
  <div class="dispatch-card-header">🚛 차량 {idx} &nbsp;
    <span class="dispatch-badge badge-warn">로베드 특수차량</span>
  </div>
  <p style="font-size:13px;color:var(--text-color);opacity:0.8;margin:0;">
    제품 높이 2.6m 이상 전용 특수 차량입니다. 물류팀에 직접 문의하세요.
  </p>
</div>
""", unsafe_allow_html=True)
                    continue

                weight_ok   = truck.get("weight_ok", True)
                rv          = truck.get("load_ratio_vol", 0)
                rw          = truck.get("load_ratio_wt",  0)
                a_plt       = truck.get("assigned_plt", 0)
                a_wkg       = truck.get("assigned_weight_kg", 0.0)
                max_wton    = truck.get("max_weight_ton")

                status_badge = (
                    '<span class="dispatch-badge badge-ok">중량 OK</span>'
                    if weight_ok else
                    '<span class="dispatch-badge badge-warn">⚠️ 중량 초과</span>'
                )

                vol_fill_cls = "ratio-bar-fill-ok" if rv <= 90 else ("ratio-bar-fill-warn" if rv <= 100 else "ratio-bar-fill-over")
                wt_fill_cls  = "ratio-bar-fill-ok" if rw <= 90 else ("ratio-bar-fill-warn" if rw <= 100 else "ratio-bar-fill-over")
                vol_pct      = min(rv, 100)
                wt_pct       = min(rw, 100)

                max_wton_str = f"{max_wton} ton" if max_wton else "정보없음"
                wt_row_html  = ""
                if max_wton:
                    wt_row_html = f"""
  <div class="dispatch-row">
    <div class="dispatch-cell" style="flex:2;">
      <div class="dispatch-cell-label">중량 적재율</div>
      <div class="dispatch-cell-value">{rw:.1f}%</div>
      <div class="ratio-bar-wrap"><div class="{wt_fill_cls}" style="width:{wt_pct}%;"></div></div>
      <div class="dispatch-cell-sub">{a_wkg/1000:.2f} ton / {max_wton_str}</div>
    </div>
    <div class="dispatch-cell" style="flex:2;">
      <div class="dispatch-cell-label">부피 적재율</div>
      <div class="dispatch-cell-value">{rv:.1f}%</div>
      <div class="ratio-bar-wrap"><div class="{vol_fill_cls}" style="width:{vol_pct}%;"></div></div>
      <div class="dispatch-cell-sub">{a_plt} PLT / {truck['max_plt']} PLT</div>
    </div>
  </div>"""

                warn_html = ""
                if not weight_ok:
                    warn_html = f"""
  <div style="margin-top:8px;padding:8px 12px;background:rgba(234,179,8,0.12);
              border-left:3px solid #f59e0b;border-radius:6px;
              font-size:12px;color:var(--text-color);">
    ⚠️ 적재 중량 {a_wkg/1000:.2f}ton 이 차량 허용 중량 {max_wton_str}을 초과합니다.
    물류팀과 별도 협의가 필요합니다.
  </div>"""

                st.markdown(f"""
<div class="dispatch-card">
  <div class="dispatch-card-header">
    🚚 차량 {idx} &nbsp;{status_badge}
  </div>
  <div class="dispatch-row">
    <div class="dispatch-cell" style="flex:3;text-align:left;">
      <div class="dispatch-cell-label">추천 차량</div>
      <div class="dispatch-cell-value" style="font-size:15px;">{truck['name']}</div>
      <div class="dispatch-cell-sub">{truck['spec']}</div>
    </div>
    <div class="dispatch-cell">
      <div class="dispatch-cell-label">배정 PLT</div>
      <div class="dispatch-cell-value">{a_plt}</div>
      <div class="dispatch-cell-sub">/ {truck['max_plt']} 최대</div>
    </div>
    <div class="dispatch-cell">
      <div class="dispatch-cell-label">배정 중량</div>
      <div class="dispatch-cell-value">{a_wkg:,.0f} kg</div>
      <div class="dispatch-cell-sub">({a_wkg/1000:.2f} ton)</div>
    </div>
  </div>
  {wt_row_html}
  {warn_html}
</div>
""", unsafe_allow_html=True)

            # ── 산출 근거 (접기) ────────────────────────────────────────────
            with st.expander("📐 산출 근거 보기"):
                for idx, truck in enumerate(trucks, 1):
                    if truck.get("is_lowbed"):
                        st.write(f"**차량 {idx}:** 로베드 특수차량")
                        continue
                    max_wton = truck.get("max_weight_ton")
                    a_plt    = truck.get("assigned_plt", 0)
                    a_wkg    = truck.get("assigned_weight_kg", 0.0)
                    weight_ok = truck.get("weight_ok", True)
                    wt_check = (
                        f"✅ {a_wkg/1000:.2f}ton ≤ {max_wton}ton (중량 OK)"
                        if weight_ok else
                        f"⚠️ {a_wkg/1000:.2f}ton > {max_wton}ton (중량 초과)"
                    ) if max_wton else "중량 정보 없음"
                    st.write(f"""**차량 {idx}: {truck['name']}**
- 적재함: {truck['spec']}
- 부피: {a_plt}PLT 배정 / 최대 {truck['max_plt']}PLT → {truck.get('load_ratio_vol',0):.1f}%
- 중량: {wt_check}""")

        # ── 자재 행 관리 세션 ───────────────────────────────────────────────
        if "dom_sim_items" not in st.session_state:
            st.session_state.dom_sim_items = [{"code": "", "qty": 1}]

        def _add_dom_item():
            st.session_state.dom_sim_items.append({"code": "", "qty": 1})

        def _del_dom_item(i):
            if len(st.session_state.dom_sim_items) > 1:
                st.session_state.dom_sim_items.pop(i)

        # ── 입력 UI ─────────────────────────────────────────────────────────
        with st.container(border=True):
            st.markdown('<div style="font-size:14px;font-weight:600;color:var(--text-color);margin:10px 0 6px 0;opacity:0.9;">📦 자재 입력</div>', unsafe_allow_html=True)
            for i, row_item in enumerate(st.session_state.dom_sim_items):
                col_code, col_qty, col_del = st.columns([3, 2, 1.2])
                with col_code:
                    new_code = st.text_input(
                        f"자재코드 {i+1}", value=row_item["code"],
                        placeholder="예: 6004216",
                        key=f"dom_code_{i}"
                    ).strip().split(".")[0].strip()
                    st.session_state.dom_sim_items[i]["code"] = new_code
                with col_qty:
                    new_qty = st.number_input(
                        f"수량{i+1} (PC)", min_value=1,
                        value=row_item["qty"],
                        key=f"dom_qty_{i}"
                    )
                    st.session_state.dom_sim_items[i]["qty"] = new_qty
                with col_del:
                    st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
                    if st.button("🗑️", key=f"dom_del_{i}",
                                 disabled=len(st.session_state.dom_sim_items) == 1,
                                 use_container_width=True):
                        _del_dom_item(i)
                        st.session_state.dom_sim_run = False  # 삭제 시 결과 초기화
                        st.rerun()

            if st.button("자재 추가 (혼적)", use_container_width=True, key="dom_add_item"):
                _add_dom_item()
                st.session_state.dom_sim_run = False  # 자재 추가 시 결과 초기화
                st.rerun()

        # ── 조회 버튼 ────────────────────────────────────────────────────────
        if "dom_sim_run" not in st.session_state:
            st.session_state.dom_sim_run = False

        if st.button("🔍 배차 조회", use_container_width=True, key="dom_run_btn"):
            st.session_state.dom_sim_run = True
            record_simulator_count("국내최적배차", team=st.session_state.get("selected_team", ""))

        # ── 계산 실행 ────────────────────────────────────────────────────────
        active_items = [
            it for it in st.session_state.dom_sim_items if it["code"].strip()
        ]

        if not active_items:
            st.info("자재코드와 수량을 입력하시면 DB 기반으로 최적 차량을 분석합니다.")
        elif not st.session_state.dom_sim_run:
            st.info("⬆️ 자재코드와 수량을 입력 후 **배차 조회** 버튼을 눌러주세요.")
        else:
            # 자재별 조회 및 검증
            resolved, errors = [], []
            for it in active_items:
                code = it["code"]
                qty  = it["qty"]
                db_item = DOM_CRAWLER_DATA.get(code)
                if not db_item:
                    partials = [c for c in DOM_CRAWLER_DATA if code in c]
                    if partials:
                        errors.append(f"**{code}**: 정확한 코드 없음. 유사: {', '.join(partials[:3])}")
                    else:
                        errors.append(f"**{code}**: DB에 없는 코드입니다.")
                    continue
                max_pc        = db_item['max_pc']
                need_plt_ceil = -(-qty // max_pc)
                weight_per_pc = db_item.get('weight_per_pc')
                total_wkg     = (weight_per_pc * qty) if weight_per_pc else 0.0
                resolved.append({
                    "code"    : code,
                    "name"    : db_item['name'],
                    "qty"     : qty,
                    "max_pc"  : max_pc,
                    "pallets" : need_plt_ceil,
                    "weight_kg": total_wkg,
                    "plt_w"   : db_item['plt_w'],
                    "plt_l"   : db_item['plt_l'],
                    "weight_per_pc": weight_per_pc,
                })

            for e in errors:
                st.warning(e)

            if resolved:
                # ── 자재별 적재 계산 카드 ─────────────────────────────────
                st.markdown('<div style="font-size:14px;font-weight:600;color:var(--text-color);margin:10px 0 6px 0;opacity:0.9;">📊 자재별 적재 계산</div>', unsafe_allow_html=True)
                for r in resolved:
                    need_plt = r['qty'] / r['max_pc']
                    plt_size = f"{int(r['plt_w']*1000)} × {int(r['plt_l']*1000)} mm"
                    w_pc     = r['weight_per_pc']
                    w_total  = r['weight_kg']

                    # 자재명 전체 표시 (잘림 방지) — 중량 셀은 사전 변수로 분리
                    if w_pc:
                        _weight_cells_dom = (
                            '<div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);'
                            'border-radius:8px;padding:7px 10px;text-align:center;">'
                            '<div style="font-size:11px;opacity:0.6;margin-bottom:2px;color:var(--text-color);">1PC 중량</div>'
                            f'<div style="font-size:14px;font-weight:700;color:var(--text-color);">{w_pc:,.1f} kg</div>'
                            '</div>'
                            '<div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);'
                            'border-radius:8px;padding:7px 10px;text-align:center;">'
                            '<div style="font-size:11px;opacity:0.6;margin-bottom:2px;color:var(--text-color);">총 중량</div>'
                            f'<div style="font-size:14px;font-weight:700;color:var(--text-color);">{w_total:,.0f} kg</div>'
                            f'<div style="font-size:11px;opacity:0.5;color:var(--text-color);">{w_total/1000:.2f} ton</div>'
                            '</div>'
                        )
                    else:
                        _weight_cells_dom = ""

                    st.markdown(f"""
<div style="border-radius:10px;padding:12px 16px;margin-bottom:10px;
            background:var(--secondary-background-color);
            border:1.5px solid rgba(128,128,128,0.15);">
  <div style="font-size:13px;font-weight:700;color:var(--text-color);
              margin-bottom:8px;line-height:1.5;word-break:break-word;">
    🏷️ {r['code']} &nbsp;<span style="opacity:0.6;font-weight:400;">|</span>&nbsp;
    {r['name']}
  </div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;">
    <div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);
                border-radius:8px;padding:7px 10px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;margin-bottom:2px;color:var(--text-color);">수량</div>
      <div style="font-size:14px;font-weight:700;color:var(--text-color);">{r['qty']} PC</div>
    </div>
    <div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);
                border-radius:8px;padding:7px 10px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;margin-bottom:2px;color:var(--text-color);">PLT당 최대</div>
      <div style="font-size:14px;font-weight:700;color:var(--text-color);">{r['max_pc']} PC</div>
    </div>
    <div style="flex:1;min-width:70px;background:rgba(59,130,246,0.1);
                border-radius:8px;padding:7px 10px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;margin-bottom:2px;color:var(--text-color);">필요 파렛트</div>
      <div style="font-size:14px;font-weight:700;color:var(--text-color);">{r['pallets']} PLT</div>
    </div>
    {_weight_cells_dom}
  </div>
  <div style="font-size:11px;opacity:0.5;margin-top:6px;color:var(--text-color);">
    📐 파렛트 {plt_size} &nbsp;|&nbsp;
    {r['qty']} ÷ {r['max_pc']} = {need_plt:.2f} → 올림 {r['pallets']} PLT
  </div>
</div>
""", unsafe_allow_html=True)

                # ── 혼적 합계 (복수 자재 시) ──────────────────────────────
                total_plt_all = sum(r['pallets'] for r in resolved)
                total_wkg_all = sum(r['weight_kg'] for r in resolved)
                if len(resolved) > 1:
                    st.markdown(f"""
<div style="border-radius:10px;padding:12px 16px;margin-bottom:14px;
            background:rgba(59,130,246,0.07);
            border:1.5px solid rgba(59,130,246,0.25);">
  <div style="font-size:13px;font-weight:700;color:var(--text-color);margin-bottom:6px;">
    📦 혼적 합계
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;">
    <div style="flex:1;min-width:80px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;color:var(--text-color);">총 파렛트</div>
      <div style="font-size:16px;font-weight:700;color:var(--text-color);">{total_plt_all} PLT</div>
    </div>
    <div style="flex:1;min-width:80px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;color:var(--text-color);">총 중량</div>
      <div style="font-size:16px;font-weight:700;color:var(--text-color);">{total_wkg_all:,.0f} kg</div>
      <div style="font-size:11px;opacity:0.5;color:var(--text-color);">{total_wkg_all/1000:.2f} ton</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

                # ── 배차 추천 (분할·혼적 통합) ────────────────────────────
                st.markdown('<div style="font-size:14px;font-weight:600;color:var(--text-color);margin:10px 0 6px 0;opacity:0.9;">🚚 최적 배차 추천</div>', unsafe_allow_html=True)
                dispatch_items = [
                    {"pallets": r["pallets"], "weight_kg": r["weight_kg"],
                     "plt_w": r["plt_w"], "plt_l": r["plt_l"]}
                    for r in resolved
                ]
                dispatch_result = get_split_dispatch_advice(dispatch_items)
                _render_dispatch_result(dispatch_result)

                # ── 버튼 행: 3D 입체 + 문의하기 ─────────────────────────
                _btn3d_dom, _btnq_dom = st.columns([1, 1])
                with _btn3d_dom:
                    if st.button("🧊 3D 입체 보기", use_container_width=True, key="dom_3d_btn"):
                        show_3d_view_popup(
                            trucks=dispatch_result.get("trucks", []),
                            resolved_items=resolved,
                            mode="truck"
                        )
                with _btnq_dom:
                    if st.button("📋 시뮬레이터 문의하기", use_container_width=True, key="dom_truck_query"):
                        trucks = dispatch_result.get("trucks", [])
                        truck_lines = "\n".join(
                            f"  차량{i+1}: {t['name']} | {t.get('assigned_plt',0)}PLT | {t.get('assigned_weight_kg',0)/1000:.2f}ton"
                            for i, t in enumerate(trucks)
                        )
                        item_lines = "\n".join(
                            f"  {r['code']} ({r['name']}) {r['qty']}PC → {r['pallets']}PLT"
                            for r in resolved
                        )
                        sim_summary = (
                            f"[자재]\n{item_lines}\n"
                            f"[합계] {total_plt_all}PLT / {total_wkg_all/1000:.2f}ton\n"
                            f"[배차]\n{truck_lines}"
                        )
                        record_sim_inquiry("국내최적배차", team=st.session_state.get("selected_team", ""))
                        show_simulator_inquiry_popup("국내 최적 배차 시뮬레이터", sim_summary)



        # ════════════════════════════════════════════════════════════════════
        # ── 🎡 컨베어벨트 배차 시뮬레이터 ──────────────────────────────────
        # ════════════════════════════════════════════════════════════════════
        st.markdown(
            '<div style="font-size:17px;font-weight:700;color:var(--text-color);margin:4px 0 2px 0;line-height:1.4;">🎡 컨베어벨트 배차 시뮬레이터</div>'
            '<hr style="height:3px;border:none;border-radius:2px;background:linear-gradient(90deg,#ff6b6b,#ffa500,#ffd700,#7ed957,#4fc3f7,#7c4dff);margin:3px 0 12px 0;">',
            unsafe_allow_html=True
        )

        # ── 컨베어벨트 DB 로드 ────────────────────────────────────────────
        @st.cache_data(ttl=300)
        def load_cb_data():
            import glob as _glob, math as _math, os as _os
            _env_path = _os.environ.get("LOGIBOT_EXCEL_PATH", "")
            search_paths = (
                ([_env_path] if _env_path and _glob.glob(_env_path) else []) +
                _glob.glob("rag_pipeline/data/source_docs/*V5*.xlsx") +
                _glob.glob("rag_pipeline/data/source_docs/*V4*.xlsx") +
                _glob.glob("rag_pipeline/data/source_docs/*.xlsx")
            )
            for path in search_paths:
                try:
                    xf = pd.ExcelFile(path)
                    cb_sheet = next((s for s in xf.sheet_names if "컨베어" in s and "규격" in s), None)
                    if not cb_sheet: continue
                    df = pd.read_excel(path, sheet_name=cb_sheet, header=0).fillna("")
                    cols = df.columns.tolist()
                    def fc(kw): return next((c for c in cols if kw in str(c)), None)
                    code_col  = fc("자재코드")
                    desc_col  = fc("자재내역")
                    grp_col   = fc("자재그룹")
                    wt_col    = fc("M당")
                    thick_col = fc("코팅후 포두께")
                    ply_col   = fc("심체수")
                    top_col   = fc("상고무")
                    bot_col   = fc("하고무")
                    width_col = fc("제품폭")
                    if not code_col: continue
                    data = {}
                    for _, row in df.iterrows():
                        code = str(row.get(code_col, "")).strip().split(".")[0].strip()
                        if not code or code in ("nan", ""): continue
                        def _f(col, default=0.0):
                            v = str(row.get(col, "")).strip() if col else ""
                            try: return float(v) if v and v != "nan" else default
                            except: return default
                        ply        = _f(ply_col)
                        thick      = _f(thick_col)
                        top_r      = _f(top_col)
                        bot_r      = _f(bot_col)
                        width_mm   = _f(width_col)
                        wt_per_m   = _f(wt_col)
                        grp        = str(row.get(grp_col, "")).strip() if grp_col else ""
                        is_steel   = "B04" in grp
                        data[code] = {
                            "name"      : str(row.get(desc_col, "")).strip() if desc_col else "",
                            "ply"       : ply,
                            "thick"     : thick,
                            "top_r"     : top_r,
                            "bot_r"     : bot_r,
                            "width_mm"  : width_mm,
                            "wt_per_m"  : wt_per_m,
                            "is_steel"  : is_steel,
                        }
                    return data
                except Exception:
                    continue
            return {}

        CB_DATA = load_cb_data()

        # ── 직경 계산 함수 ────────────────────────────────────────────────
        def calc_roll_diameter(item: dict, length_m: float) -> float:
            """
            공식: 포의 총두께 = (상고무 + 하고무) + (PLY * 코팅후포두께 - 0.2)
            롤 직경 = sqrt(총두께/1000 * 4 * 길이(m) / π + 0.09)
            B04 스틸벨트: 코팅후포두께=0 → 포두께 컬럼 사용 안 함, 별도 처리 필요
            """
            import math as _math
            ply   = item["ply"]
            thick = item["thick"]   # 코팅후 포두께
            top_r = item["top_r"]   # 상고무두께
            bot_r = item["bot_r"]   # 하고무두께

            if item["is_steel"]:
                # 스틸 벨트: ply = 심체 직경(mm), top_r = 심체수, bot_r = 하고무
                # 포의 총두께 = 심체직경(두께로 사용) + 상고무 + 하고무
                # 단: 스틸은 공식 적용 불가 → 직접 추정
                steel_dia_mm = ply        # 심체 직경 mm
                top_rubber   = bot_r      # 상고무 (구조 상 bot_r에 저장됨)
                bot_rubber   = item.get("bot_r", 5)
                total_thick  = steel_dia_mm + top_rubber + bot_rubber
            else:
                if thick > 0:
                    total_thick = (top_r + bot_r) + (ply * thick - 0.2)
                else:
                    # 코팅후 포두께 없는 경우: 포두께(mm) × ply 추정
                    total_thick = (top_r + bot_r) + ply * 1.0

            if total_thick <= 0 or length_m <= 0:
                return 0.0

            dia = _math.sqrt(total_thick / 1000.0 * 4.0 * length_m / 3.14159 + 0.09)
            return round(dia, 3)

        # ── 입력 UI ──────────────────────────────────────────────────────
        with st.container(border=True):
            st.markdown('<div style="font-size:14px;font-weight:600;color:var(--text-color);margin:10px 0 6px 0;opacity:0.9;">📦 자재 입력</div>', unsafe_allow_html=True)
            if "cb_sim_items" not in st.session_state:
                st.session_state.cb_sim_items = [{"code": "", "length": 100.0, "rolls": 1}]

            def _add_cb(): st.session_state.cb_sim_items.append({"code":"","length":100.0,"rolls":1})
            def _del_cb(i):
                if len(st.session_state.cb_sim_items) > 1:
                    st.session_state.cb_sim_items.pop(i)

            for i, cb_row in enumerate(st.session_state.cb_sim_items):
                # 1행: 자재코드 / 길이
                c1, c2 = st.columns([3, 2])
                with c1:
                    new_code = st.text_input(f"자재코드 {i+1}", value=cb_row["code"],
                        placeholder="예: 6015628", key=f"cb_code_{i}"
                    ).strip().split(".")[0].strip()
                    st.session_state.cb_sim_items[i]["code"] = new_code
                with c2:
                    new_len = st.number_input(f"길이(m) {i+1}", min_value=0.1, value=float(cb_row["length"]),
                        step=10.0, key=f"cb_len_{i}")
                    st.session_state.cb_sim_items[i]["length"] = new_len
                # 2행: 롤 수 / 삭제 버튼
                c3, c4 = st.columns([4, 1.2])
                with c3:
                    new_rolls = st.number_input(f"롤 수 {i+1}", min_value=1, value=int(cb_row["rolls"]),
                        step=1, key=f"cb_rolls_{i}")
                    st.session_state.cb_sim_items[i]["rolls"] = new_rolls
                with c4:
                    st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
                    if st.button("🗑️", key=f"cb_del_{i}",
                                 disabled=len(st.session_state.cb_sim_items)==1,
                                 use_container_width=True):
                        _del_cb(i)
                        st.session_state.cb_sim_run = False  # 삭제 시 결과 초기화
                        st.rerun()

            if st.button("롤 추가", use_container_width=True, key="cb_add"):
                _add_cb()
                st.session_state.cb_sim_run = False  # 롤 추가 시 결과 초기화
                st.rerun()

        # ── 조회 버튼 ─────────────────────────────────────────────────────
        if "cb_sim_run" not in st.session_state:
            st.session_state.cb_sim_run = False

        if st.button("🔍 롤 직경 / 배차 조회", use_container_width=True, key="cb_run_btn"):
            st.session_state.cb_sim_run = True
            record_simulator_count("컨베어벨트배차", team=st.session_state.get("selected_team", ""))

        # ── 계산 ─────────────────────────────────────────────────────────
        cb_active = [it for it in st.session_state.cb_sim_items if it["code"].strip()]
        if not cb_active:
            st.info("자재코드, 길이(m), 롤 수를 입력하면 롤 직경과 적합 차량을 계산합니다.")
        elif not st.session_state.cb_sim_run:
            st.info("⬆️ 자재코드와 수치를 입력 후 **롤 직경 / 배차 조회** 버튼을 눌러주세요.")
        else:
            cb_resolved, cb_errors = [], []
            for it in cb_active:
                code  = it["code"]
                l_m   = it["length"]
                rolls = it["rolls"]
                db    = CB_DATA.get(code)
                if not db:
                    partials = [c for c in CB_DATA if code in c]
                    cb_errors.append(f"**{code}**: {'유사: '+', '.join(partials[:3]) if partials else 'DB에 없음'}")
                    continue
                dia = calc_roll_diameter(db, l_m)
                wt  = db["wt_per_m"] * l_m if db["wt_per_m"] else 0
                cb_resolved.append({
                    "code": code, "name": db["name"], "length_m": l_m,
                    "rolls": rolls, "dia_m": dia, "width_mm": db["width_mm"],
                    "wt_per_roll": wt, "total_wt": wt * rolls,
                    "is_steel": db["is_steel"],
                })

            for e in cb_errors:
                st.warning(e)

            if cb_resolved:
                st.markdown('<div style="font-size:14px;font-weight:600;color:var(--text-color);margin:10px 0 6px 0;opacity:0.9;">📊 롤 직경 계산 결과</div>', unsafe_allow_html=True)
                for r in cb_resolved:
                    _type  = "🔩 스틸벨트" if r["is_steel"] else "🎡 포벨트"
                    _dia_c = "#ef4444" if r["dia_m"] >= 2.6 else ("#f59e0b" if r["dia_m"] >= 2.0 else "#3b82f6")
                    _warn  = "⚠️ 로베드 차량 필요!" if r["dia_m"] >= 2.6 else ("주의" if r["dia_m"] >= 2.0 else "")
                    _wt_cells = ""
                    if r["wt_per_roll"]:
                        _wt_cells = (
                            '<div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);'
                            'border-radius:8px;padding:7px 10px;text-align:center;">'
                            '<div style="font-size:11px;opacity:0.6;color:var(--text-color);">롤당 중량</div>'
                            f'<div style="font-size:13px;font-weight:700;color:var(--text-color);">{r["wt_per_roll"]:,.0f} kg</div>'
                            '</div>'
                            '<div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);'
                            'border-radius:8px;padding:7px 10px;text-align:center;">'
                            '<div style="font-size:11px;opacity:0.6;color:var(--text-color);">총 중량</div>'
                            f'<div style="font-size:13px;font-weight:700;color:var(--text-color);">{r["total_wt"]:,.0f} kg</div>'
                            f'<div style="font-size:11px;opacity:0.5;color:var(--text-color);">{r["total_wt"]/1000:.2f} ton</div>'
                            '</div>'
                        )
                    st.markdown(f"""
<div style="border-radius:10px;padding:12px 16px;margin-bottom:10px;
            background:var(--secondary-background-color);
            border:1.5px solid rgba(128,128,128,0.15);">
  <div style="font-size:13px;font-weight:700;color:var(--text-color);margin-bottom:8px;word-break:break-word;">
    {_type} &nbsp;🏷️ {r["code"]} | {r["name"][:30]}
  </div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;">
    <div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);border-radius:8px;padding:7px 10px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;color:var(--text-color);">길이</div>
      <div style="font-size:13px;font-weight:700;color:var(--text-color);">{r["length_m"]:.0f} m</div>
    </div>
    <div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);border-radius:8px;padding:7px 10px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;color:var(--text-color);">롤 수</div>
      <div style="font-size:13px;font-weight:700;color:var(--text-color);">{r["rolls"]} 롤</div>
    </div>
    <div style="flex:1;min-width:70px;background:rgba(59,130,246,0.10);border-radius:8px;padding:7px 10px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;color:var(--text-color);">롤 직경</div>
      <div style="font-size:15px;font-weight:700;color:{_dia_c};">{r["dia_m"]:.3f} m</div>
      <div style="font-size:11px;color:{_dia_c};">{int(r["dia_m"]*1000)} mm {"　"+_warn if _warn else ""}</div>
    </div>
    <div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);border-radius:8px;padding:7px 10px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;color:var(--text-color);">제품 폭</div>
      <div style="font-size:13px;font-weight:700;color:var(--text-color);">{int(r["width_mm"])} mm</div>
    </div>
    {_wt_cells}
  </div>
</div>
""", unsafe_allow_html=True)

                # ── 차량 추천 (직경 기준, 1열 상차) ─────────────────────
                st.markdown('<div style="font-size:14px;font-weight:600;color:var(--text-color);margin:10px 0 6px 0;opacity:0.9;">🚚 적합 차량 추천</div>', unsafe_allow_html=True)

                # 최대 직경 롤 기준으로 차량 결정
                max_dia  = max(r["dia_m"] for r in cb_resolved)
                tot_wt   = sum(r["total_wt"] for r in cb_resolved)
                tot_rolls= sum(r["rolls"] for r in cb_resolved)
                max_width_m = max(r["width_mm"] for r in cb_resolved) / 1000

                if max_dia >= 2.6:
                    st.error(
                        f"🚛 **로베드(Low-bed) 차량 필요** | 최대 직경 {max_dia:.3f}m (≥ 2.6m)\n\n"
                        "제품 높이 2.6m 이상은 로베드 전용 특수 차량이 필요합니다. 물류팀에 직접 문의하세요."
                    )
                else:
                    # 직경(높이)과 폭 기준으로 적합 차량 필터
                    # 1열 상차 차량 필터 기준:
                    # - 폭: 차량 적재함 폭 ≥ max(롤 직경, 제품 폭)
                    #   (롤이 둥글기 때문에 직경이 곧 필요 폭)
                    # - 높이: 컨베어벨트 롤은 적재함 위로 돌출 가능
                    #   도로법 기준 지상 최대 4.0m / 차량 바닥 높이 약 1.2m
                    #   → 최대 허용 직경 = 4.0 - 1.2 = 2.8m
                    #   → 2.6m 이상은 이미 로베드 분기에서 처리됨
                    #   따라서 여기서는 높이 체크 불필요 (폭·중량만 체크)
                    # - 길이: 직경 × 롤 수 (1열 배치)
                    # - 중량: 총 중량 ≤ 차량 최대 허용 중량
                    CB_VEHICLES = [
                        {"name":"1톤(1.2톤)", "wt":1.32, "length":2.8, "width":1.6,  "height":2.2},
                        {"name":"2.5톤",      "wt":2.75, "length":4.3, "width":1.8,  "height":2.2},
                        {"name":"3.5톤(신규)","wt":3.85, "length":4.8, "width":2.0,  "height":2.2},
                        {"name":"5톤",        "wt":5.5,  "length":6.2, "width":2.34, "height":2.2},
                        {"name":"8톤",        "wt":8.2,  "length":7.4, "width":2.34, "height":2.2},
                        {"name":"11톤",       "wt":12.0, "length":9.0, "width":2.34, "height":2.2},
                        {"name":"18톤",       "wt":19.0, "length":10.1,"width":2.34, "height":2.2},
                        {"name":"25톤",       "wt":25.5, "length":10.1,"width":2.34, "height":2.2},
                        {"name":"트레일러",   "wt":25.0, "length":12.0,"width":2.34, "height":2.2},
                    ]
                    candidates = []
                    for v in CB_VEHICLES:
                        # 폭 체크: 적재함 폭 ≥ max(롤 직경, 제품 폭)
                        need_w = max(max_dia, max_width_m)
                        if v["width"] < need_w:
                            continue
                        # 길이 체크: 직경 × 롤 수
                        need_l = max_dia * tot_rolls
                        vol_ok = v["length"] >= need_l
                        wt_ok  = (tot_wt / 1000) <= v["wt"]
                        candidates.append({**v, "need_l": need_l, "vol_ok": vol_ok, "wt_ok": wt_ok})

                    ok_both = [c for c in candidates if c["vol_ok"] and c["wt_ok"]]
                    ok_vol  = [c for c in candidates if not c["wt_ok"]]

                    if ok_both:
                        best_cb = ok_both[0]
                        need_l  = best_cb["need_l"]
                        st.success(f"**추천 차량: {best_cb['name']}**")
                        _height_note = ""
                        if max_dia > best_cb["height"]:
                            _ground_h = 1.2 + max_dia
                            _height_note = (
                                f"  \n⚠️ 롤 직경({max_dia:.2f}m)이 적재함 높이({best_cb['height']}m)를 초과 → "
                                f"상단 돌출 상차 | 지상 높이 약 {_ground_h:.2f}m (도로법 4.0m 이하 ✅)"
                            )
                        st.markdown(
                            f"📏 적재함 {best_cb['length']}m × {best_cb['width']}m | "
                            f"⚖️ 최대 {best_cb['wt']}ton | "
                            f"🎡 롤 1열 필요 길이 {need_l:.2f}m ({max_dia:.2f}m × {tot_rolls}롤)"
                            + _height_note
                        )
                    elif candidates:
                        best_cb = candidates[0]
                        need_l  = best_cb["need_l"]
                        st.warning(
                            f"⚠️ **{best_cb['name']}** (중량 초과 가능성) | "
                            f"총 중량 {tot_wt/1000:.2f}ton / 허용 {best_cb['wt']}ton"
                        )
                    else:
                        best_cb = None
                        need_l  = max_dia * tot_rolls
                        st.warning("⚠️ 적합한 일반 차량이 없습니다. 직경/중량 초과 — 물류팀에 문의하세요.")

                    # ── 3D 버튼 ───────────────────────────────────────────
                    if best_cb and st.button("🧊 3D 입체 보기 (컨베어벨트)", use_container_width=True, key="cb_3d_btn"):
                        import plotly.graph_objects as _go
                        import math as _math
                        import numpy as _np

                        _fig = _go.Figure()
                        car_l = best_cb["length"]
                        car_w = best_cb["width"]
                        car_h = best_cb["height"]

                        # 적재함 외곽
                        for _tr in _make_wireframe(car_l, car_w, car_h, "#888888"):
                            _fig.add_trace(_tr)
                        # 바닥
                        _fig.add_trace(_go.Mesh3d(
                            x=[0,car_l,car_l,0], y=[0,0,car_w,car_w], z=[0,0,0,0],
                            i=[0,0], j=[1,2], k=[2,3],
                            color="#CCCCCC", opacity=0.12, showlegend=False, hoverinfo="skip"
                        ))

                        # 가이드라인: 높이 2.6m
                        if 2.6 <= car_h + 0.5:
                            _fig.add_trace(_go.Scatter3d(
                                x=[0, car_l, car_l, 0, 0],
                                y=[0, 0, car_w, car_w, 0],
                                z=[2.6]*5,
                                mode="lines",
                                line=dict(color="#ef4444", width=3, dash="dash"),
                                name="⚠️ 높이 2.6m (로베드 기준)",
                                showlegend=True, hoverinfo="name"
                            ))

                        # 롤 원통 렌더링 (근사: 다각형 실린더)
                        _theta  = _np.linspace(0, 2*_np.pi, 32)
                        _cx     = 0.0   # 시작 위치 (X=길이 방향)
                        _PALETTE_CB = ["#4C9BE8","#F4845F","#63C9A8","#E8C34C","#A878D8"]

                        for ri, r in enumerate(cb_resolved):
                            _dia  = r["dia_m"]
                            _r    = _dia / 2
                            _w_m  = r["width_mm"] / 1000  # 벨트 폭 = 실린더 길이(Y축)
                            _color = _PALETTE_CB[ri % len(_PALETTE_CB)]
                            _yc   = _w_m / 2   # 폭 방향 중심
                            _zc   = _r         # 높이 방향 중심(바닥에서 반지름)

                            for roll_i in range(r["rolls"]):
                                _xc  = _cx + _r
                                _lbl = (f"{r['code']} 롤{roll_i+1} (Ø{_dia:.2f}m)"
                                        if roll_i == 0 else f"__hidden_cb_{ri}_{roll_i}")
                                _is_hid = _lbl.startswith("__hidden")

                                # ── Surface로 완전한 원통 렌더링 ──────────────
                                # theta: 0~2π를 SEG+1개 (endpoint=True → 마지막=첫점, 완전 닫힘)
                                # x축(길이방향): [앞면 X, 뒷면 X] 2개
                                _SEG  = 60   # 더 많은 분할로 매끄러운 원
                                _angs = _np.linspace(0, 2*_np.pi, _SEG + 1)  # SEG+1로 닫힌 원
                                _cos  = _np.cos(_angs)
                                _sin  = _np.sin(_angs)

                                # Surface: x[2, SEG+1], y[2, SEG+1], z[2, SEG+1]
                                _sx = _np.array([
                                    [_xc]       * (_SEG + 1),  # 앞면
                                    [_xc + _w_m] * (_SEG + 1), # 뒷면
                                ])
                                _sy = _np.array([
                                    _yc + _r * _cos,
                                    _yc + _r * _cos,
                                ])
                                _sz = _np.array([
                                    _zc + _r * _sin,
                                    _zc + _r * _sin,
                                ])

                                # hex color → rgb tuple for colorscale
                                import struct as _struct
                                _hx = _color.lstrip('#')
                                _cr, _cg, _cb_v = tuple(int(_hx[i:i+2], 16) for i in (0,2,4))
                                _cscale = [[0, f'rgb({_cr},{_cg},{_cb_v})'],
                                           [1, f'rgb({_cr},{_cg},{_cb_v})']]

                                _fig.add_trace(_go.Surface(
                                    x=_sx, y=_sy, z=_sz,
                                    colorscale=_cscale,
                                    showscale=False,
                                    opacity=0.80,
                                    name="" if _is_hid else _lbl,
                                    showlegend=not _is_hid,
                                    hovertemplate=(
                                        f"<b>{r['code']}</b><br>"
                                        f"직경: {_dia:.3f}m | 폭: {r['width_mm']:.0f}mm<br>"
                                        f"중량: {r['wt_per_roll']:,.0f}kg<extra></extra>"
                                        if not _is_hid else "<extra></extra>"
                                    ),
                                    contours=dict(
                                        x=dict(highlight=False),
                                        y=dict(highlight=False),
                                        z=dict(highlight=False),
                                    )
                                ))

                                # 앞면·뒷면 원 테두리 (Surface가 자동 닫히지만 테두리 강조)
                                for _x0 in [_xc, _xc + _w_m]:
                                    _fig.add_trace(_go.Scatter3d(
                                        x=[_x0] * (_SEG + 1),
                                        y=list(_sy[0]),
                                        z=list(_sz[0]),
                                        mode="lines",
                                        line=dict(color=_color, width=2),
                                        showlegend=False, hoverinfo="skip"
                                    ))

                                _cx += _dia   # 다음 롤 위치

                        _fig.update_layout(
                            scene=dict(
                                xaxis=dict(range=[0, car_l], title="길이 (m)"),
                                yaxis=dict(range=[0, car_w], title="폭 (m)"),
                                zaxis=dict(range=[0, max(car_h, max_dia+0.2)], title="높이 (m)"),
                                aspectmode="manual",
                                aspectratio=dict(x=max(car_l,0.1)/max(car_w,0.1), y=1,
                                                 z=max(car_h,0.1)/max(car_w,0.1)),
                                camera=dict(eye=dict(x=1.5, y=-2.0, z=1.3))
                            ),
                            margin=dict(l=0,r=0,b=0,t=30),
                            legend=dict(font=dict(size=11), x=0, y=1)
                        )

                        # 안내 카드
                        _guide_h = (
                            '<div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap;">'
                            f'<div style="flex:1;min-width:110px;background:rgba(59,130,246,0.08);border-radius:8px;padding:7px 12px;border:1.5px solid rgba(59,130,246,0.2);">'
                            f'<div style="font-size:11px;opacity:0.6;color:var(--text-color);">추천 차량</div>'
                            f'<div style="font-size:14px;font-weight:700;color:var(--text-color);">{best_cb["name"]}</div>'
                            f'<div style="font-size:11px;opacity:0.5;color:var(--text-color);">{best_cb["length"]}m × {best_cb["width"]}m</div></div>'
                            f'<div style="flex:1;min-width:110px;background:rgba(128,128,128,0.06);border-radius:8px;padding:7px 12px;border:1.5px solid rgba(128,128,128,0.15);">'
                            f'<div style="font-size:11px;opacity:0.6;color:var(--text-color);">최대 직경</div>'
                            f'<div style="font-size:14px;font-weight:700;color:var(--text-color);">{max_dia:.3f} m</div>'
                            f'<div style="font-size:11px;opacity:0.5;color:var(--text-color);">{int(max_dia*1000)} mm</div></div>'
                            f'<div style="flex:1;min-width:110px;background:rgba(128,128,128,0.06);border-radius:8px;padding:7px 12px;border:1.5px solid rgba(128,128,128,0.15);">'
                            f'<div style="font-size:11px;opacity:0.6;color:var(--text-color);">총 롤 수 / 중량</div>'
                            f'<div style="font-size:14px;font-weight:700;color:var(--text-color);">{tot_rolls} 롤</div>'
                            f'<div style="font-size:11px;opacity:0.5;color:var(--text-color);">{tot_wt:,.0f} kg ({tot_wt/1000:.2f} ton)</div></div>'
                            '</div>'
                        )
                        st.session_state["cb_3d_data"] = {
                            "fig": _fig,
                            "guide_html": _guide_h,
                        }
                        show_cb_3d_popup()

    elif current_team == "트랙영업팀":
        st.markdown(
            '<div style="font-size:17px;font-weight:700;color:var(--text-color);margin:4px 0 2px 0;line-height:1.4;">🚜 크롤러 배차 시뮬레이터</div>'
            '<hr style="height:3px;border:none;border-radius:2px;background:linear-gradient(90deg,#ff6b6b,#ffa500,#ffd700,#7ed957,#4fc3f7,#7c4dff);margin:3px 0 12px 0;">',
            unsafe_allow_html=True
        )

        # ── DB(Excel)에서 크롤러 자재 데이터 로드 ──────────────────────────
        @st.cache_data(ttl=300)
        def load_crawler_data():
            """
            V3 기준:
              - 파일명: Logibot-Data_기본__V3__1_.xlsx
              - 시트명: '크롤러 러버트랙 규격 데이터'
              - 헤더:   1행 (0행은 섹션 제목 '[크롤러 러버트랙 자재 데이터]')
            파일/시트명이 달라져도 자동 탐지
            """
            import glob as _glob, os as _os

            CRAWLER_SHEET_KEYWORD = "크롤러"

            _env_path = _os.environ.get("LOGIBOT_EXCEL_PATH", "")
            search_paths = (
                ([_env_path] if _env_path and _glob.glob(_env_path) else []) +
                _glob.glob("rag_pipeline/data/source_docs/*V5*.xlsx") +
                _glob.glob("rag_pipeline/data/source_docs/*V4*.xlsx") +
                _glob.glob("rag_pipeline/data/source_docs/*V3*.xlsx") +
                _glob.glob("rag_pipeline/data/source_docs/*.xlsx")
            )

            df = None
            for path in search_paths:
                try:
                    xf = pd.ExcelFile(path)
                    crawler_sheet = next(
                        (s for s in xf.sheet_names if CRAWLER_SHEET_KEYWORD in s),
                        None
                    )
                    if not crawler_sheet:
                        continue
                    df_test = pd.read_excel(path, sheet_name=crawler_sheet, header=0, nrows=2)
                    first_col = str(df_test.columns[0])
                    if first_col.startswith("[") or "Unnamed" in first_col:
                        df = pd.read_excel(path, sheet_name=crawler_sheet, header=1).fillna("")
                    else:
                        df = pd.read_excel(path, sheet_name=crawler_sheet, header=0).fillna("")
                    break
                except Exception:
                    continue

            if df is None:
                return {}

            cols = df.columns.tolist()
            def find_col(kw):
                return next((c for c in cols if kw in str(c)), None)

            code_col   = find_col("자재코드")
            name_col   = find_col("자재내역")
            qty_col    = find_col("최대 적재 수량") or find_col("적재 수량")
            size_col   = find_col("사이즈")
            weight_col = find_col("중량") or find_col("KG") or find_col("kg")

            if not code_col:
                return {}

            data = {}
            for _, row in df.iterrows():
                code = str(row.get(code_col, "")).strip().split(".")[0].strip()
                if not code or code in ("nan", ""):
                    continue
                size_raw = str(row.get(size_col, "1000*1100")).strip() if size_col else "1000*1100"
                try:
                    w_mm, l_mm = [float(x) for x in size_raw.replace("×", "*").split("*")]
                except Exception:
                    w_mm, l_mm = 1000.0, 1100.0
                try:
                    max_pc = int(float(str(row.get(qty_col, 1)).strip())) if qty_col else 1
                except Exception:
                    max_pc = 1
                weight_per_pc = None
                if weight_col:
                    try:
                        val = str(row.get(weight_col, "")).strip()
                        if val and val not in ("nan", ""):
                            weight_per_pc = float(val)
                    except Exception:
                        weight_per_pc = None
                data[code] = {
                    "name"         : str(row.get(name_col, "")).strip() if name_col else "",
                    "max_pc"       : max_pc,
                    "plt_w"        : w_mm / 1000,
                    "plt_l"        : l_mm / 1000,
                    "weight_per_pc": weight_per_pc,
                }
            return data

        CRAWLER_DATA = load_crawler_data()

        # ── 자재 행 관리 세션 ───────────────────────────────────────────────
        if "trk_sim_items" not in st.session_state:
            st.session_state.trk_sim_items = [{"code": "", "qty": 1}]

        def _add_trk_item():
            st.session_state.trk_sim_items.append({"code": "", "qty": 1})

        def _del_trk_item(i):
            if len(st.session_state.trk_sim_items) > 1:
                st.session_state.trk_sim_items.pop(i)

        # ── 입력 UI ─────────────────────────────────────────────────────────
        with st.container(border=True):
            st.markdown('<div style="font-size:14px;font-weight:600;color:var(--text-color);margin:10px 0 6px 0;opacity:0.9;">📦 자재 입력</div>', unsafe_allow_html=True)
            for i, row_item in enumerate(st.session_state.trk_sim_items):
                col_code, col_qty, col_del = st.columns([3, 2, 1.2])
                with col_code:
                    new_code = st.text_input(
                        f"자재코드 {i+1}", value=row_item["code"],
                        placeholder="예: 6004216",
                        key=f"trk_code_{i}"
                    ).strip().split(".")[0].strip()
                    st.session_state.trk_sim_items[i]["code"] = new_code
                with col_qty:
                    new_qty = st.number_input(
                        f"수량{i+1} (PC)", min_value=1,
                        value=row_item["qty"],
                        key=f"trk_qty_{i}"
                    )
                    st.session_state.trk_sim_items[i]["qty"] = new_qty
                with col_del:
                    st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
                    if st.button("🗑️", key=f"trk_del_{i}",
                                 disabled=len(st.session_state.trk_sim_items) == 1,
                                 use_container_width=True):
                        _del_trk_item(i)
                        st.session_state.trk_sim_run = False  # 삭제 시 결과 초기화
                        st.rerun()

            if st.button("자재 추가 (혼적)", use_container_width=True, key="trk_add_item"):
                _add_trk_item()
                st.session_state.trk_sim_run = False  # 자재 추가 시 결과 초기화
                st.rerun()

        # ── 조회 버튼 ────────────────────────────────────────────────────────
        if "trk_sim_run" not in st.session_state:
            st.session_state.trk_sim_run = False

        if st.button("🔍 배차 조회", use_container_width=True, key="trk_run_btn"):
            st.session_state.trk_sim_run = True
            record_simulator_count("크롤러배차", team=st.session_state.get("selected_team", ""))

        # ── 계산 실행 ────────────────────────────────────────────────────────
        trk_active = [it for it in st.session_state.trk_sim_items if it["code"].strip()]

        if not trk_active:
            st.info("자재코드와 수량을 입력하시면 DB 기반으로 최적 차량을 분석합니다.")
        elif not st.session_state.trk_sim_run:
            st.info("⬆️ 자재코드와 수량을 입력 후 **배차 조회** 버튼을 눌러주세요.")
        else:
            resolved_trk, errors_trk = [], []
            for it in trk_active:
                code = it["code"]
                qty  = it["qty"]
                db_item = CRAWLER_DATA.get(code)
                if not db_item:
                    partials = [c for c in CRAWLER_DATA if code in c]
                    if partials:
                        errors_trk.append(f"**{code}**: 정확한 코드 없음. 유사: {', '.join(partials[:3])}")
                    else:
                        errors_trk.append(f"**{code}**: DB에 없는 코드입니다.")
                    continue
                max_pc        = db_item['max_pc']
                need_plt_ceil = -(-qty // max_pc)
                weight_per_pc = db_item.get('weight_per_pc')
                total_wkg     = (weight_per_pc * qty) if weight_per_pc else 0.0
                resolved_trk.append({
                    "code"    : code,
                    "name"    : db_item['name'],
                    "qty"     : qty,
                    "max_pc"  : max_pc,
                    "pallets" : need_plt_ceil,
                    "weight_kg": total_wkg,
                    "plt_w"   : db_item['plt_w'],
                    "plt_l"   : db_item['plt_l'],
                    "weight_per_pc": weight_per_pc,
                })

            for e in errors_trk:
                st.warning(e)

            if resolved_trk:
                # ── 자재별 적재 계산 카드 ─────────────────────────────────
                st.markdown('<div style="font-size:14px;font-weight:600;color:var(--text-color);margin:10px 0 6px 0;opacity:0.9;">📊 자재별 적재 계산</div>', unsafe_allow_html=True)
                for r in resolved_trk:
                    need_plt = r['qty'] / r['max_pc']
                    plt_size = f"{int(r['plt_w']*1000)} × {int(r['plt_l']*1000)} mm"
                    w_pc     = r['weight_per_pc']
                    w_total  = r['weight_kg']

                    # 중량 셀은 사전 변수로 분리 (중첩 f-string 회피)
                    if w_pc:
                        _weight_cells_trk = (
                            '<div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);'
                            'border-radius:8px;padding:7px 10px;text-align:center;">'
                            '<div style="font-size:11px;opacity:0.6;margin-bottom:2px;color:var(--text-color);">1PC 중량</div>'
                            f'<div style="font-size:14px;font-weight:700;color:var(--text-color);">{w_pc:,.1f} kg</div>'
                            '</div>'
                            '<div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);'
                            'border-radius:8px;padding:7px 10px;text-align:center;">'
                            '<div style="font-size:11px;opacity:0.6;margin-bottom:2px;color:var(--text-color);">총 중량</div>'
                            f'<div style="font-size:14px;font-weight:700;color:var(--text-color);">{w_total:,.0f} kg</div>'
                            f'<div style="font-size:11px;opacity:0.5;color:var(--text-color);">{w_total/1000:.2f} ton</div>'
                            '</div>'
                        )
                    else:
                        _weight_cells_trk = ""

                    st.markdown(f"""
<div style="border-radius:10px;padding:12px 16px;margin-bottom:10px;
            background:var(--secondary-background-color);
            border:1.5px solid rgba(128,128,128,0.15);">
  <div style="font-size:13px;font-weight:700;color:var(--text-color);
              margin-bottom:8px;line-height:1.5;word-break:break-word;">
    🏷️ {r['code']} &nbsp;<span style="opacity:0.6;font-weight:400;">|</span>&nbsp;
    {r['name']}
  </div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;">
    <div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);
                border-radius:8px;padding:7px 10px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;margin-bottom:2px;color:var(--text-color);">수량</div>
      <div style="font-size:14px;font-weight:700;color:var(--text-color);">{r['qty']} PC</div>
    </div>
    <div style="flex:1;min-width:70px;background:rgba(128,128,128,0.08);
                border-radius:8px;padding:7px 10px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;margin-bottom:2px;color:var(--text-color);">PLT당 최대</div>
      <div style="font-size:14px;font-weight:700;color:var(--text-color);">{r['max_pc']} PC</div>
    </div>
    <div style="flex:1;min-width:70px;background:rgba(40,167,69,0.12);
                border-radius:8px;padding:7px 10px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;margin-bottom:2px;color:var(--text-color);">필요 파렛트</div>
      <div style="font-size:14px;font-weight:700;color:var(--text-color);">{r['pallets']} PLT</div>
    </div>
    {_weight_cells_trk}
  </div>
  <div style="font-size:11px;opacity:0.5;margin-top:6px;color:var(--text-color);">
    📐 파렛트 {plt_size} &nbsp;|&nbsp;
    {r['qty']} ÷ {r['max_pc']} = {need_plt:.2f} → 올림 {r['pallets']} PLT
  </div>
</div>
""", unsafe_allow_html=True)

                total_plt_trk = sum(r['pallets'] for r in resolved_trk)
                total_wkg_trk = sum(r['weight_kg'] for r in resolved_trk)
                if len(resolved_trk) > 1:
                    st.markdown(f"""
<div style="border-radius:10px;padding:12px 16px;margin-bottom:14px;
            background:rgba(40,167,69,0.07);
            border:1.5px solid rgba(40,167,69,0.25);">
  <div style="font-size:13px;font-weight:700;color:var(--text-color);margin-bottom:6px;">
    📦 혼적 합계
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;">
    <div style="flex:1;min-width:80px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;color:var(--text-color);">총 파렛트</div>
      <div style="font-size:16px;font-weight:700;color:var(--text-color);">{total_plt_trk} PLT</div>
    </div>
    <div style="flex:1;min-width:80px;text-align:center;">
      <div style="font-size:11px;opacity:0.6;color:var(--text-color);">총 중량</div>
      <div style="font-size:16px;font-weight:700;color:var(--text-color);">{total_wkg_trk:,.0f} kg</div>
      <div style="font-size:11px;opacity:0.5;color:var(--text-color);">{total_wkg_trk/1000:.2f} ton</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

                # ── 배차 추천 ────────────────────────────────────────────
                st.markdown('<div style="font-size:14px;font-weight:600;color:var(--text-color);margin:10px 0 6px 0;opacity:0.9;">🚚 최적 배차 추천</div>', unsafe_allow_html=True)
                dispatch_items_trk = [
                    {"pallets": r["pallets"], "weight_kg": r["weight_kg"],
                     "plt_w": r["plt_w"], "plt_l": r["plt_l"]}
                    for r in resolved_trk
                ]

                # _render_dispatch_result는 국내 시뮬레이터와 공유
                dispatch_result_trk = get_split_dispatch_advice(dispatch_items_trk)

                trucks_t           = dispatch_result_trk.get("trucks", [])
                is_split_t         = dispatch_result_trk.get("split", False)
                error_t            = dispatch_result_trk.get("error")

                if error_t:
                    st.warning(f"⚠️ {error_t}")
                elif not trucks_t:
                    st.warning("⚠️ 적합한 차량이 없습니다. 물류팀에 직접 문의하세요.")
                else:
                    split_badge_t = (
                        '<span class="dispatch-badge badge-split">🔀 분할 배차</span>'
                        if is_split_t else
                        '<span class="dispatch-badge badge-ok">✅ 단일 배차</span>'
                    )
                    st.markdown(f"""
<div class="dispatch-summary-box">
  <strong>배차 요약</strong> &nbsp;{split_badge_t}<br>
  <span style="opacity:0.7;">총 파렛트 {total_plt_trk} PLT &nbsp;|&nbsp;
  총 중량 {total_wkg_trk:,.0f} kg ({total_wkg_trk/1000:.2f} ton) &nbsp;|&nbsp;
  차량 {len(trucks_t)}대</span>
</div>
""", unsafe_allow_html=True)

                    for idx, truck in enumerate(trucks_t, 1):
                        if truck.get("is_lowbed"):
                            st.markdown(f"""
<div class="dispatch-card">
  <div class="dispatch-card-header">🚛 차량 {idx} &nbsp;
    <span class="dispatch-badge badge-warn">로베드 특수차량</span>
  </div>
  <p style="font-size:13px;color:var(--text-color);opacity:0.8;margin:0;">
    제품 높이 2.6m 이상 전용 특수 차량입니다. 물류팀에 직접 문의하세요.
  </p>
</div>
""", unsafe_allow_html=True)
                            continue

                        weight_ok_t = truck.get("weight_ok", True)
                        rv_t   = truck.get("load_ratio_vol", 0)
                        rw_t   = truck.get("load_ratio_wt",  0)
                        a_plt_t = truck.get("assigned_plt", 0)
                        a_wkg_t = truck.get("assigned_weight_kg", 0.0)
                        max_wton_t = truck.get("max_weight_ton")

                        s_badge_t = (
                            '<span class="dispatch-badge badge-ok">중량 OK</span>'
                            if weight_ok_t else
                            '<span class="dispatch-badge badge-warn">⚠️ 중량 초과</span>'
                        )
                        vfc_t = "ratio-bar-fill-ok" if rv_t <= 90 else ("ratio-bar-fill-warn" if rv_t <= 100 else "ratio-bar-fill-over")
                        wfc_t = "ratio-bar-fill-ok" if rw_t <= 90 else ("ratio-bar-fill-warn" if rw_t <= 100 else "ratio-bar-fill-over")
                        max_wton_str_t = f"{max_wton_t} ton" if max_wton_t else "정보없음"

                        wt_row_t = ""
                        if max_wton_t:
                            wt_row_t = f"""
  <div class="dispatch-row">
    <div class="dispatch-cell" style="flex:2;">
      <div class="dispatch-cell-label">중량 적재율</div>
      <div class="dispatch-cell-value">{rw_t:.1f}%</div>
      <div class="ratio-bar-wrap"><div class="{wfc_t}" style="width:{min(rw_t,100)}%;"></div></div>
      <div class="dispatch-cell-sub">{a_wkg_t/1000:.2f} ton / {max_wton_str_t}</div>
    </div>
    <div class="dispatch-cell" style="flex:2;">
      <div class="dispatch-cell-label">부피 적재율</div>
      <div class="dispatch-cell-value">{rv_t:.1f}%</div>
      <div class="ratio-bar-wrap"><div class="{vfc_t}" style="width:{min(rv_t,100)}%;"></div></div>
      <div class="dispatch-cell-sub">{a_plt_t} PLT / {truck['max_plt']} PLT</div>
    </div>
  </div>"""

                        warn_t = ""
                        if not weight_ok_t:
                            warn_t = f"""
  <div style="margin-top:8px;padding:8px 12px;background:rgba(234,179,8,0.12);
              border-left:3px solid #f59e0b;border-radius:6px;
              font-size:12px;color:var(--text-color);">
    ⚠️ 적재 중량 {a_wkg_t/1000:.2f}ton이 허용 중량 {max_wton_str_t}을 초과합니다. 물류팀과 협의하세요.
  </div>"""

                        st.markdown(f"""
<div class="dispatch-card">
  <div class="dispatch-card-header">🚚 차량 {idx} &nbsp;{s_badge_t}</div>
  <div class="dispatch-row">
    <div class="dispatch-cell" style="flex:3;text-align:left;">
      <div class="dispatch-cell-label">추천 차량</div>
      <div class="dispatch-cell-value" style="font-size:15px;">{truck['name']}</div>
      <div class="dispatch-cell-sub">{truck['spec']}</div>
    </div>
    <div class="dispatch-cell">
      <div class="dispatch-cell-label">배정 PLT</div>
      <div class="dispatch-cell-value">{a_plt_t}</div>
      <div class="dispatch-cell-sub">/ {truck['max_plt']} 최대</div>
    </div>
    <div class="dispatch-cell">
      <div class="dispatch-cell-label">배정 중량</div>
      <div class="dispatch-cell-value">{a_wkg_t:,.0f} kg</div>
      <div class="dispatch-cell-sub">({a_wkg_t/1000:.2f} ton)</div>
    </div>
  </div>
  {wt_row_t}
  {warn_t}
</div>
""", unsafe_allow_html=True)

                    with st.expander("📐 산출 근거 보기"):
                        for idx, truck in enumerate(trucks_t, 1):
                            if truck.get("is_lowbed"):
                                st.write(f"**차량 {idx}:** 로베드 특수차량")
                                continue
                            max_wton_t2 = truck.get("max_weight_ton")
                            a_plt_t2    = truck.get("assigned_plt", 0)
                            a_wkg_t2    = truck.get("assigned_weight_kg", 0.0)
                            wok_t2      = truck.get("weight_ok", True)
                            wt_chk = (
                                f"✅ {a_wkg_t2/1000:.2f}ton ≤ {max_wton_t2}ton (중량 OK)"
                                if wok_t2 else
                                f"⚠️ {a_wkg_t2/1000:.2f}ton > {max_wton_t2}ton (중량 초과)"
                            ) if max_wton_t2 else "중량 정보 없음"
                            st.write(f"""**차량 {idx}: {truck['name']}**
- 적재함: {truck['spec']}
- 부피: {a_plt_t2}PLT / 최대 {truck['max_plt']}PLT → {truck.get('load_ratio_vol',0):.1f}%
- 중량: {wt_chk}""")

                # ── 버튼 행: 3D 입체 + 문의하기 ─────────────────────────
                _btn3d_trk, _btnq_trk = st.columns([1, 1])
                with _btn3d_trk:
                    if st.button("🧊 3D 입체 보기", use_container_width=True, key="trk_3d_btn"):
                        show_3d_view_popup(
                            trucks=dispatch_result_trk.get("trucks", []),
                            resolved_items=resolved_trk,
                            mode="truck"
                        )
                with _btnq_trk:
                    if st.button("📋 시뮬레이터 문의하기", use_container_width=True, key="trk_truck_query"):
                        trucks_t2 = dispatch_result_trk.get("trucks", [])
                        truck_lines_t = "\n".join(
                            f"  차량{i+1}: {t['name']} | {t.get('assigned_plt',0)}PLT | {t.get('assigned_weight_kg',0)/1000:.2f}ton"
                            for i, t in enumerate(trucks_t2)
                        )
                        item_lines_t = "\n".join(
                            f"  {r['code']} ({r['name']}) {r['qty']}PC → {r['pallets']}PLT"
                            for r in resolved_trk
                        )
                        sim_summary_t = (
                            f"[자재]\n{item_lines_t}\n"
                            f"[합계] {total_plt_trk}PLT / {total_wkg_trk/1000:.2f}ton\n"
                            f"[배차]\n{truck_lines_t}"
                        )
                        record_sim_inquiry("크롤러배차", team=st.session_state.get("selected_team", ""))
                        show_simulator_inquiry_popup("크롤러 배차 시뮬레이터", sim_summary_t)
                       
# ── 개선 요청 버튼 & 팝업 ────────────────────────────────────────────────
if "show_improve_form" not in st.session_state:
    st.session_state.show_improve_form = False
if "improve_submitted" not in st.session_state:
    st.session_state.improve_submitted = False

# 버튼 행: 오른쪽 정렬을 위해 컬럼 분할
_btn_spacer, _btn_col = st.columns([7, 1])
with _btn_col:
    if st.button("💡 개선 요청", use_container_width=True, key="open_improve_form"):
        st.session_state.show_improve_form = not st.session_state.show_improve_form
        st.session_state.improve_submitted = False

# 팝업 말풍선
if st.session_state.show_improve_form:
    with st.container(border=True):
        st.markdown(
            "<p style='font-size:15px;font-weight:700;margin-bottom:4px;'>💡 개선 요청하기</p>"
            "<p style='font-size:12px;color:#888;margin-top:0;'>기능 개선, 오류 신고, 아이디어 등 자유롭게 작성해주세요.</p>",
            unsafe_allow_html=True
        )
        improve_author = st.text_input(
            "✍️ 작성자", placeholder="이름을 입력하세요",
            max_chars=30, key="improve_author_input"
        )
        improve_text = st.text_area(
            label="내용 입력",
            placeholder="예) 특정 자재코드 검색 시 결과가 없습니다.\n예) 운임 계산에 ○○ 지역이 추가되면 좋겠습니다.",
            height=130,
            key="improve_text_input",
            label_visibility="collapsed"
        )
        _sub_col, _cancel_col = st.columns([1, 1])
        with _sub_col:
            if st.button("📨 제출하기", use_container_width=True, key="submit_improve"):
                if not improve_author.strip():
                    st.warning("작성자를 입력해주세요.")
                elif not improve_text.strip():
                    st.warning("내용을 입력해주세요.")
                else:
                    current_team_for_mail = st.session_state.get("selected_team", "전체")
                    full_content = f"[작성자: {improve_author.strip()}]\n\n{improve_text.strip()}"
                    try:
                        success = EMAIL_NOTIFIER.send_improvement_request(
                            content=full_content,
                            team=current_team_for_mail
                        )
                    except Exception:
                        success = False
                    st.session_state.improve_submitted = True
                    st.session_state.show_improve_form = False
                    if success:
                        st.toast(f"✅ 개선 요청이 담당자에게 전달되었습니다! ({improve_author.strip()})", icon="💡")
                    else:
                        st.toast("⚠️ 전송에 실패했습니다. 직접 담당자에게 문의해주세요.", icon="⚠️")
                    st.rerun()
        with _cancel_col:
            if st.button("✖ 취소", use_container_width=True, key="cancel_improve"):
                st.session_state.show_improve_form = False
                st.rerun()

st.title("📦 DRB LOGIBOT-AI")

# ═══════════════════════════════════════════════════════════════
# 📰 실시간 뉴스 티커 (브라우저 JS fetch + URL 동적 조립)
# ═══════════════════════════════════════════════════════════════
import streamlit.components.v1 as _components
import json as _json

# 팀별 설정: JS에서 encodeURIComponent로 URL 조립하므로 쿼리는 원문 그대로
_NEWS_CFG = {
    "국내영업팀": {
        "label": "🚚 국내 물류 뉴스",
        "color": "#007BFF",
        "queries": [
            # ── 구글뉴스 (단순 키워드) ──────────────────────────────────
            {"q": "물류",           "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "운임",           "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "택배",           "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "화물",           "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "배송",           "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "물류센터",       "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "공급망",         "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "항만",           "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            # ── 전문 RSS (직접 피드) ────────────────────────────────────
            {"url": "https://www.klnews.co.kr/rss/allArticle.xml",  "type": "rss", "label": "국토물류신문"},
            {"url": "https://www.transportnews.co.kr/rss/allArticle.xml", "type": "rss", "label": "교통신문"},
        ],
    },
    "해외영업팀": {
        "label": "🚢 해외 물류·국제정세 뉴스",
        "color": "#FF8C00",
        "queries": [
            # ── 구글뉴스 (단순 키워드) ──────────────────────────────────
            {"q": "해상운임",       "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "컨테이너",       "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "수출입",         "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "관세",           "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "무역",           "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "선박",           "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "공급망",         "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "홍해",           "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            # ── 영문 구글뉴스 ───────────────────────────────────────────
            {"q": "shipping freight", "hl": "en", "gl": "US", "ceid": "US:en", "type": "google"},
            {"q": "container rates",  "hl": "en", "gl": "US", "ceid": "US:en", "type": "google"},
            # ── 전문 RSS (직접 피드) ────────────────────────────────────
            {"url": "https://www.klnews.co.kr/rss/allArticle.xml",  "type": "rss", "label": "국토물류신문"},
        ],
    },
    "트랙영업팀": {
        "label": "🚜 건설기계 뉴스",
        "color": "#28A745",
        "queries": [
            # ── 구글뉴스 (단순 키워드) ──────────────────────────────────
            {"q": "건설기계",       "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "굴삭기",         "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "크롤러",         "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "중장비",         "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "건설장비",       "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            {"q": "컨베어벨트",     "hl": "ko", "gl": "KR", "ceid": "KR:ko", "type": "google"},
            # ── 전문 RSS (직접 피드) ────────────────────────────────────
            {"url": "https://www.cmnews.co.kr/rss/allArticle.xml",  "type": "rss", "label": "CM건설기계신문"},
        ],
    },
}

def render_news_ticker(team: str):
    cfg = _NEWS_CFG.get(team)
    if not cfg:
        return

    label = cfg["label"]
    color = cfg["color"]
    queries_json = _json.dumps(cfg["queries"], ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:transparent; font-family:'Malgun Gothic',-apple-system,sans-serif; overflow:hidden; }}
  .wrap {{
    display:flex; align-items:center;
    background:rgba(40,40,40,0.55);
    border:1px solid rgba(128,128,128,0.25);
    border-radius:10px; overflow:hidden;
    height:40px;
  }}
  .lbl {{
    flex-shrink:0; background:{color};
    color:#fff; font-size:11px; font-weight:700;
    padding:0 12px; height:40px;
    display:flex; align-items:center;
    white-space:nowrap; border-radius:10px 0 0 10px;
  }}
  .body {{ flex:1; overflow:hidden; height:40px; position:relative; min-width:0; }}
  .ticker-a {{
    position:absolute; top:50%; left:0; right:0;
    transform:translateY(-50%);
    display:block; padding:0 14px;
    font-size:13px; font-weight:500; color:#e8e8e8;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
    text-decoration:none; transition:opacity 0.3s ease;
  }}
  .ticker-a:hover {{ color:{color}; text-decoration:underline; }}
  .nav {{
    flex-shrink:0; display:flex; align-items:center;
    padding:0 5px; height:40px;
    border-left:1px solid rgba(128,128,128,0.2); gap:1px;
  }}
  .nav button {{
    background:transparent; border:none; color:#999;
    font-size:11px; cursor:pointer; padding:3px 5px;
    border-radius:4px; transition:all 0.15s;
  }}
  .nav button:hover {{ background:rgba(255,255,255,0.1); color:#fff; }}
  .cnt {{ font-size:10px; color:#777; padding:0 3px; min-width:24px; text-align:center; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="lbl">{label}</div>
  <div class="body">
    <a class="ticker-a" id="ta" href="#" target="_blank" rel="noopener noreferrer">뉴스 불러오는 중...</a>
  </div>
  <div class="nav">
    <button onclick="go(-1)">&#9650;</button>
    <span class="cnt" id="cnt">-</span>
    <button onclick="go(1)">&#9660;</button>
  </div>
</div>

<script>
var QUERIES = {queries_json};
var items = [];
var idx = 0;
var timer = null;
var el = document.getElementById('ta');
var cntEl = document.getElementById('cnt');

// 구글뉴스 RSS URL 조립 (JS encodeURIComponent 사용 → 이중인코딩 없음)
function buildGoogleRssUrl(qObj) {{
  return 'https://news.google.com/rss/search?q=' + encodeURIComponent(qObj.q)
    + '&hl=' + qObj.hl + '&gl=' + qObj.gl + '&ceid=' + encodeURIComponent(qObj.ceid);
}}

function stripHtml(s) {{
  return s.replace(/<[^>]+>/g, '').replace(/ +/g, ' ').trim();
}}

// ── 날짜 파싱: rss2json 형식 + RSS 표준 형식 모두 처리
// rss2json: "2025-04-21 03:15:00"
// RSS 표준:  "Mon, 21 Apr 2025 03:15:00 +0000"
function parseDate(s) {{
  if (!s) return null;
  var t = s.trim();
  // rss2json 형식: "YYYY-MM-DD HH:MM:SS" → T + Z 붙여 UTC 파싱
  if (/^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}} [0-9]{{2}}:/.test(t)) {{
    t = t.replace(' ', 'T') + 'Z';
  }}
  var d = new Date(t);
  return isNaN(d.getTime()) ? null : d;
}}

// 현재 시각 기준 30일 이내 — 파싱 실패 시 true로 처리(기사 포함)
function isWithin30Days(pubStr) {{
  var d = parseDate(pubStr);
  if (!d) return true;
  return (Date.now() - d.getTime()) <= 30 * 24 * 60 * 60 * 1000;
}}

// ── rss2json JSON 파싱
function parseRss2json(data) {{
  var out = [];
  if (!data || !data.items) return out;
  data.items.forEach(function(it) {{
    if (!isWithin30Days(it.pubDate)) return;
    var t = stripHtml(it.title || '').replace(/ *- *[^-]*$/, '').trim();
    if (t.length < 5) return;
    out.push({{ title: t, link: it.link || it.guid || '#', pub: it.pubDate || '' }});
  }});
  return out;
}}

// ── XML(DOMParser) 파싱 — allorigins / corsproxy 대응
function parseXml(xmlText) {{
  var out = [];
  try {{
    var doc = new DOMParser().parseFromString(xmlText, 'text/xml');
    var nodes = doc.querySelectorAll('item');
    nodes.forEach(function(node) {{
      var pub = (node.querySelector('pubDate') || {{}}).textContent || '';
      if (!isWithin30Days(pub)) return;
      var t = stripHtml((node.querySelector('title') || {{}}).textContent || '');
      t = t.replace(/ *- *[^-]*$/, '').trim();
      if (t.length < 5) return;
      var link = (node.querySelector('link') || {{}}).textContent
               || (node.querySelector('guid') || {{}}).textContent || '#';
      // CDATA link 처리
      if (!link || link.trim() === '') {{
        var ln = node.getElementsByTagName('link')[0];
        if (ln) link = ln.textContent || ln.getAttribute('href') || '#';
      }}
      out.push({{ title: t, link: link.trim(), pub: pub }});
    }});
  }} catch(e) {{}}
  return out;
}}

// ── 프록시 fallback 체인
// 1순위: rss2json (JSON, 빠름)
// 2순위: allorigins (XML, 안정적)
// 3순위: corsproxy.io (XML)
function buildProxies(rssUrl) {{
  var enc = encodeURIComponent(rssUrl);
  return [
    {{
      url: 'https://api.rss2json.com/v1/api.json?rss_url=' + enc + '&count=30',
      type: 'json'
    }},
    {{
      url: 'https://api.allorigins.win/raw?url=' + enc,
      type: 'xml'
    }},
    {{
      url: 'https://corsproxy.io/?' + enc,
      type: 'xml'
    }},
  ];
}}

// ── 프록시 순차 시도
function fetchRss(proxies, pi, onSuccess, onFail) {{
  if (pi >= proxies.length) {{ onFail(); return; }}
  var p = proxies[pi];
  fetch(p.url)
    .then(function(r) {{ return r.ok ? (p.type === 'json' ? r.json() : r.text()) : Promise.reject(r.status); }})
    .then(function(data) {{
      var parsed = p.type === 'json' ? parseRss2json(data) : parseXml(data);
      if (parsed.length > 0) {{ onSuccess(parsed); }}
      else {{ fetchRss(proxies, pi + 1, onSuccess, onFail); }}
    }})
    .catch(function() {{ fetchRss(proxies, pi + 1, onSuccess, onFail); }});
}}

// ── 중복 제거 후 items에 추가
function mergeItems(parsed) {{
  var added = 0;
  parsed.forEach(function(it) {{
    if (items.length >= 50) return;  // 최대 50개로 확대
    var key = it.title.replace(/ /g, '').slice(0, 15);
    var dup = items.some(function(x) {{ return x.title.replace(/ /g, '').slice(0, 15) === key; }});
    if (!dup) {{ items.push(it); added++; }}
  }});
  return added;
}}

// ── 쿼리별 순차 로드 (google / rss 타입 분기)
function tryLoad(qi) {{
  if (qi >= QUERIES.length) {{
    if (items.length === 0) el.textContent = '뉴스를 가져올 수 없습니다';
    return;
  }}
  var q = QUERIES[qi];

  // RSS 직접 피드 (전문 언론사)
  if (q.type === 'rss') {{
    var enc = encodeURIComponent(q.url);
    var proxies = [
      {{ url: 'https://api.rss2json.com/v1/api.json?rss_url=' + enc + '&count=30', type: 'json' }},
      {{ url: 'https://api.allorigins.win/raw?url=' + enc, type: 'xml' }},
      {{ url: 'https://corsproxy.io/?' + enc, type: 'xml' }},
    ];
    fetchRss(proxies, 0,
      function(parsed) {{
        var added = mergeItems(parsed);
        if (items.length > 0 && qi === 0) {{ show(0); startTimer(); }}
        else if (added > 0) {{ cntEl.textContent = (idx+1)+'/'+items.length; }}
        tryLoad(qi + 1);
      }},
      function() {{ tryLoad(qi + 1); }}
    );
    return;
  }}

  // 구글뉴스 RSS
  var rssUrl  = buildGoogleRssUrl(q);
  var proxies = buildProxies(rssUrl);
  fetchRss(proxies, 0,
    function(parsed) {{
      var added = mergeItems(parsed);
      if (items.length > 0 && qi === 0) {{ show(0); startTimer(); }}
      else if (added > 0) {{ cntEl.textContent = (idx+1)+'/'+items.length; }}
      tryLoad(qi + 1);
    }},
    function() {{ tryLoad(qi + 1); }}
  );
}}

function show(i) {{
  if (items.length === 0) return;
  idx = ((i % items.length) + items.length) % items.length;
  el.style.opacity = '0';
  setTimeout(function() {{
    el.textContent = items[idx].title;
    el.href = items[idx].link;
    el.style.opacity = '1';
    cntEl.textContent = (idx+1) + '/' + items.length;
  }}, 280);
}}

function go(dir) {{
  show(idx + dir);
  if (timer) clearInterval(timer);
  startTimer();
}}

function startTimer() {{
  if (timer) clearInterval(timer);
  timer = setInterval(function() {{ show(idx + 1); }}, 5500);
}}

tryLoad(0);
</script>
</body>
</html>"""

    _components.html(html, height=48, scrolling=False)


_ticker_team = st.session_state.get("selected_team", "국내영업팀")
if _ticker_team in ("국내영업팀", "해외영업팀", "트랙영업팀"):
    render_news_ticker(_ticker_team)

# ═══════════════════════════════════════════════════════════════
curr_conv = st.session_state.conversations[st.session_state.current_id]

# --- 추천 질문 표시 (첫 메시지(인사말)만 있을 때) ---
current_team = st.session_state.get("selected_team", "국내영업팀")
suggestions = TEAM_SUGGESTIONS.get(current_team, [])

if len(curr_conv["messages"]) == 1 and st.session_state.show_suggestions:
    for row in range(3):
        col1, col2 = st.columns(2)
        with col1:
            idx1 = row * 2
            if idx1 < len(suggestions):
                if st.button(f"{suggestions[idx1]}", key=f"sugg_{current_team}_{idx1}", use_container_width=True):
                    st.session_state.pending_query = suggestions[idx1]
                    st.rerun()
        with col2:
            idx2 = row * 2 + 1
            if idx2 < len(suggestions):
                if st.button(f"{suggestions[idx2]}", key=f"sugg_{current_team}_{idx2}", use_container_width=True):
                    st.session_state.pending_query = suggestions[idx2]
                    st.rerun()

# 메시지 표시
for idx, msg in enumerate(curr_conv["messages"]):
    # ⚠️ 렌더링 시 re.sub 제거 — format_answer(query_processor)에서 이미 처리됨
    # 이중 적용 시 실제 수치(1.234톤, 0.892 등)까지 삭제되어 답변이 공백이 되는 원인
    clean_content = msg["content"]

    if msg["role"] == "user":
        # ✅ 사용자 질문 버블
        with st.container():
            st.markdown(f'<div class="chat-bubble user">{clean_content}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="message-timestamp" style="text-align:right;">{msg["timestamp"][-8:-3]}</div>', unsafe_allow_html=True)

    elif msg["role"] == "assistant":
        body_html, _ = format_answer_display(clean_content, msg.get("has_table", False))
        
        with st.container():
            st.markdown(f'<div class="chat-bubble assistant">{body_html}</div>', unsafe_allow_html=True)

        st.markdown(f'<div class="message-timestamp">{msg["timestamp"][-8:-3]}</div>', unsafe_allow_html=True)
        
        # 피드백 및 복사 버튼 (첫 어시스턴트 인사말 제외)
        if idx > 0:
            c1, c2, c3, c4, _ = st.columns([0.5, 0.5, 1.2, 1.5, 3])
            with c1:
                if st.button("👍", key=f"up_{idx}"):
                    if (st.session_state.current_id, idx) not in st.session_state.feedback_done:
                        submit_feedback(
                            curr_conv["messages"][idx-1]["content"], 
                            1.0, 
                            msg["content"], 
                            [],
                            team=st.session_state.get("selected_team", "")
                        )
                        st.session_state.feedback_done.add((st.session_state.current_id, idx))
                        st.toast("긍정적인 피드백 감사합니다!")
            with c2:
                if st.button("👎", key=f"down_{idx}"):
                    if (st.session_state.current_id, idx) not in st.session_state.feedback_done:
                        last_user_q = ""
                        for prev in reversed(curr_conv["messages"][:idx]):
                            if prev["role"] == "user":
                                last_user_q = prev["content"]
                                break
                        show_bad_feedback_popup(idx, last_user_q, msg["content"])
            with c3:
                raw_text = re.sub('<[^<]+?>', '', msg["content"])
                st.download_button("📋", data=raw_text, file_name="answer.txt", key=f"cp_{idx}")
            with c4:
                sources = msg.get("sources", [])
                btn_label = f"📎 참고문서 ({len(sources)})" if sources else "📎 참고문서"
                if st.button(btn_label, key=f"src_{idx}", disabled=not sources):
                    last_user_msg = ""
                    # 해당 답변 직전의 사용자 질문 찾기
                    for prev in reversed(curr_conv["messages"][:idx]):
                        if prev["role"] == "user":
                            last_user_msg = prev["content"]
                            break
                    # ④ 참고문서 클릭 카운트
                    _aid = msg.get("answer_id", "")
                    if _aid:
                        record_doc_click(_aid)
                    show_source_popup(sources, last_user_msg)
        
# --- 대기 중인 질문 처리 ---
if st.session_state.pending_query and not st.session_state.is_generating:
    query = st.session_state.pending_query
    st.session_state.pending_query = None
    process_user_query(query)

# --- 입력 처리 ---
input_placeholder = (
    "⏳ 답변 생성 중... 입력하면 완료 후 자동 처리됩니다"
    if st.session_state.is_generating
    else "물류 업무에 대해 질문하세요"
)
if prompt := st.chat_input(input_placeholder):
    user_query = re.sub(r'\s?\d\.\d{3}\s?', '', prompt).strip()
    if st.session_state.is_generating:
        # 생성 중이면 대기열에 저장
        st.session_state.queued_query = user_query
        st.toast("⏳ 이전 답변 완료 후 자동으로 처리됩니다.", icon="⏳")
    else:
        process_user_query(user_query)