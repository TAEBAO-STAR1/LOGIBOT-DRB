import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
import re
import pandas as pd
import plotly.express as px

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

# 2. 팀별 색상
st.markdown(f"""
<style>
    .team-container {{ display: flex; justify-content: center; gap: 15px; margin-bottom: 30px; }}
    .team-card {{
        flex: 1; text-align: center; padding: 15px; border-radius: 12px;
        color: white; font-weight: bold; cursor: pointer; transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 2px solid transparent;
    }}
    /* 부서별 고유 색상 및 호버 적용 */
    .btn-dom {{ background-color: {TEAM_CONFIG["국내영업팀"]["color"]}; }}
    .btn-dom:hover {{ background-color: {TEAM_CONFIG["국내영업팀"]["hover"]}; transform: translateY(-3px); box-shadow: 0 6px 12px rgba(0,0,0,0.2); }}
    
    .btn-int {{ background-color: {TEAM_CONFIG["해외영업팀"]["color"]}; }}
    .btn-int:hover {{ background-color: {TEAM_CONFIG["해외영업팀"]["hover"]}; transform: translateY(-3px); }}
    
    .btn-track {{ background-color: {TEAM_CONFIG["트랙영업팀"]["color"]}; }}
    .btn-track:hover {{ background-color: {TEAM_CONFIG["트랙영업팀"]["hover"]}; transform: translateY(-3px); }}
    
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
            selected = [REASON_LABELS[k] for k, v in reasons.items() if v]
            reason_text = " / ".join(selected) if selected else "사유 미입력"
            if extra.strip():
                reason_text += f" | 추가의견: {extra.strip()}"

            if (st.session_state.current_id, msg_idx) not in st.session_state.feedback_done:
                submit_feedback(query, 0.0, answer, [], reason=reason_text)
                st.session_state.feedback_done.add((st.session_state.current_id, msg_idx))

            st.toast("피드백이 반영되었습니다. 감사합니다! 🙏")
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

# ── 배차 추천 결과 공통 렌더 함수 ────────────────────────────────────────
def render_truck_advice(best_truck, need_plt_ceil: int, total_weight_kg: float,
                        weight_per_pc, key_prefix: str = ""):
    """
    get_db_transport_advice 반환값을 렌더링.
    단일 차량(dict) / 다중 차량({"multi": True, ...}) / 로베드 모두 처리.
    다크·라이트 모드 모두 대응 (CSS 변수 사용).
    """
    if not best_truck:
        st.warning("⚠️ 적합한 차량이 없습니다. 물류팀에 직접 문의하세요.")
        return

    total_weight_ton = total_weight_kg / 1000.0

    def _card(label: str, value: str, sub: str = "", color: str = "#3b82f6") -> str:
        sub_html = (
            f"<div style='font-size:13px;color:var(--text-color);opacity:0.55;"
            f"margin-top:4px;'>{sub}</div>"
        ) if sub else ""
        return f"""
<div style="flex:1 1 120px;min-width:120px;background:var(--secondary-background-color);
     border-radius:10px;padding:14px 16px;border-left:3px solid {color};
     overflow-wrap:break-word;word-break:break-word;">
  <div style="font-size:13px;color:var(--text-color);opacity:0.55;margin-bottom:6px;">{label}</div>
  <div style="font-size:20px;font-weight:700;color:var(--text-color);line-height:1.3;">{value}</div>
  {sub_html}
</div>"""

    def _progress_bar(ratio: float) -> str:
        bar_pct   = min(ratio, 100)
        bar_color = "#22c55e" if ratio < 80 else "#f59e0b" if ratio <= 100 else "#ef4444"
        return f"""
<div style="margin:10px 0 4px;">
  <div style="display:flex;justify-content:space-between;align-items:center;
       font-size:14px;color:var(--text-color);margin-bottom:5px;">
    <span style="opacity:0.65;">적재율</span>
    <span style="font-weight:700;color:{bar_color};font-size:18px;">{ratio:.1f}%</span>
  </div>
  <div style="background:var(--secondary-background-color);border-radius:99px;
       height:10px;overflow:hidden;">
    <div style="width:{bar_pct:.1f}%;background:{bar_color};
         height:10px;border-radius:99px;"></div>
  </div>
</div>"""

    # ── 로베드 ───────────────────────────────────────────────────────────
    if best_truck.get("is_lowbed"):
        st.info("🚛 **로베드(Low-bed) 차량**\n\n제품 높이 2.6m 이상인 경우 선택하는 특수 차량입니다. 물류팀에 직접 문의하세요.")
        return

    # ── 다중 차량 ────────────────────────────────────────────────────────
    if best_truck.get("multi"):
        trucks = best_truck['trucks']
        ratio  = best_truck['load_ratio']
        st.success(f"**최적 배차: {best_truck['desc']}**")
        for i, t in enumerate(trucks, 1):
            wt_str     = f"{t['wt_ton']:.2f} ton" if t.get('wt_ton') else "-"
            max_wt_str = f"{t['max_wt']} ton"     if t.get('max_wt') else "-"
            border_color = '#10b981' if i == 1 else '#6366f1'
            icon = '🚛' if i == 1 else '🚐'
            st.markdown(f"""
<div style="background:var(--secondary-background-color);border-radius:10px;
     padding:14px 16px;margin-bottom:8px;border-left:4px solid {border_color};">
  <div style="font-size:16px;font-weight:700;color:var(--text-color);margin-bottom:10px;">
    {icon} 차량 {i} — {t['name']}
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:8px;">
    <div style="flex:1 1 90px;min-width:90px;background:var(--background-color);
         border-radius:8px;padding:10px 12px;text-align:center;">
      <div style="font-size:12px;color:var(--text-color);opacity:0.55;margin-bottom:3px;">📦 적재</div>
      <div style="font-size:18px;font-weight:700;color:var(--text-color);">{t['plt']} PLT</div>
    </div>
    <div style="flex:1 1 90px;min-width:90px;background:var(--background-color);
         border-radius:8px;padding:10px 12px;text-align:center;">
      <div style="font-size:12px;color:var(--text-color);opacity:0.55;margin-bottom:3px;">⚖️ 중량</div>
      <div style="font-size:16px;font-weight:700;color:var(--text-color);">{wt_str}</div>
      <div style="font-size:12px;color:var(--text-color);opacity:0.55;margin-top:2px;">최대 {max_wt_str}</div>
    </div>
    <div style="flex:1 1 90px;min-width:90px;background:var(--background-color);
         border-radius:8px;padding:10px 12px;text-align:center;">
      <div style="font-size:12px;color:var(--text-color);opacity:0.55;margin-bottom:3px;">📏 제원</div>
      <div style="font-size:14px;font-weight:600;color:var(--text-color);
           word-break:break-all;line-height:1.3;">{t['spec']}</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)
        st.markdown(_progress_bar(ratio), unsafe_allow_html=True)
        return

    # ── 단일 차량 ────────────────────────────────────────────────────────
    ratio = best_truck.get('load_ratio', round((need_plt_ceil / best_truck['max_plt']) * 100, 1))

    st.success(f"**추천 차량: {best_truck['name']}**")

    cards_html = '<div style="display:flex;gap:10px;margin:8px 0;flex-wrap:wrap;">'
    cards_html += _card("📏 적재함 제원", best_truck['spec'], color="#6366f1")
    cards_html += _card("📦 최대 적재",   f"{best_truck['max_plt']} PLT", color="#10b981")
    if best_truck.get('max_weight_ton'):
        cards_html += _card("⚖️ 최대 중량", f"{best_truck['max_weight_ton']} ton", color="#f59e0b")
    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)

    st.markdown(_progress_bar(ratio), unsafe_allow_html=True)

    if best_truck.get('plt_over'):
        st.warning(
            f"⚠️ 파렛트 배열 기준({best_truck['max_plt']} PLT)을 초과하지만 "
            f"총 중량({total_weight_ton:.2f} ton)은 허용 범위 내입니다. "
            f"현장 적재 방식 조정 후 단일 차량 운행이 가능합니다. 물류팀에 확인하세요."
        )
    elif weight_per_pc and not best_truck.get('weight_ok', True):
        st.warning(
            f"⚠️ 총 중량 {total_weight_ton:.2f} ton이 차량 최대 허용 중량을 초과합니다. "
            f"물류팀에 별도 협의가 필요합니다."
        )

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
    from rag_pipeline.query_processor import get_rag_response, submit_feedback, analyze_logistics_data, analyze_pdf_logistics, get_db_transport_advice, EMAIL_NOTIFIER
    import logging
    logger = logging.getLogger(__name__)
except ImportError:
    def get_rag_response(q, context=None): return {"answer": "답변입니다.", "has_table": False}
    def submit_feedback(q, s, c, src): pass
    def get_db_transport_advice(p, w=0): return None
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
    curr_conv = st.session_state.conversations[st.session_state.current_id]

    # [중복 방지]
    if curr_conv["messages"] and curr_conv["messages"][-1].get("content") == query:
        return

    # [생성 중 보호] — 이미 LLM 호출 중이면 대기열에 저장하고 종료
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

    try:
        # 4. 답변 생성
        with st.spinner("🤖 답변 생성 중... (다른 메뉴를 클릭하면 완료 후 반영됩니다)"):
            response   = get_rag_response(query, context=curr_conv.get("context", []))
            answer_text = response.get('answer', "")

            curr_conv["messages"].append({
                "role"      : "assistant",
                "content"   : answer_text,
                "sources"   : response.get('sources', []),
                "timestamp" : datetime.now().isoformat(),
                "has_table" : response.get('has_table', False)
            })

            # 5. 대화 컨텍스트 누적 (최대 10턴)
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
        # 6. 생성 완료 — 무조건 플래그 해제 (예외 발생해도 잠금 풀림)
        st.session_state.is_generating = False

    # 7. 대기 중인 질문이 있으면 pending으로 넘겨 다음 rerun에서 처리
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
            '<span style="font-size:11px;">완료 후 다른 메뉴가 활성화됩니다</span>'
            '</div>',
            unsafe_allow_html=True
        )

    # 1. 부서 선택 탭 (최상단 고정)
    st.markdown("### 🏢 부서 모드 선택")
    team_options = {"국내영업팀": "🚚", "해외영업팀": "🚢", "트랙영업팀": "🚜"}

    generating = st.session_state.is_generating   # 짧은 alias
    team_cols = st.columns(3)
    for idx, (t_name, t_icon) in enumerate(team_options.items()):
        is_selected = (st.session_state.selected_team == t_name)
        # 생성 중이면 버튼 비활성화
        btn_clicked = team_cols[idx].button(
            f"{t_icon}\n{t_name[:2]}",
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
    st.markdown("---")

    st.title("💬 대화 목록")
    
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

        search_paths = (
            _glob.glob("data/source_docs/*V4*.xlsx") +
            _glob.glob("data/source_docs/*V3*.xlsx") +
            _glob.glob("data/source_docs/*.xlsx") +
            _glob.glob("/mnt/user-data/uploads/*V4*.xlsx") +
            _glob.glob("/mnt/user-data/uploads/*.xlsx")
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
    # PLT당 박스 수 기본값 (추후 DB 시트 추가 시 확장 가능)
    GROUP_PALLET_LIMIT = {"B01": 20, "B02": 20, "N18": 20, "N19": 20}

    current_team = st.session_state.selected_team

    if current_team == "해외영업팀":
        st.subheader("📦 수출 포장량 시뮬레이터", divider="rainbow")

        with st.container(border=True):
            total_target_weight = st.number_input(
                "목표 총 중량 (kg)", min_value=0.0, value=800.0, step=10.0
            )
            selected_packing = st.selectbox(
                "포장재 종류",
                options=["선택하세요"] + (PACKING_LIST or [
                    "제품-650박스","제품-1090박스","제품-세미박스",
                    "제품-마대","제품-600박스",
                    "슬리브-650박스","슬리브-세미박스","슬리브-600박스"
                ])
            )
            # ── 복수 자재그룹 선택 (multiselect) ──────────────────────────
            selected_groups = st.multiselect(
                "자재그룹 (복수 선택 가능)",
                options=GROUP_LIST or ["B01","B02","N18","N19"],
                placeholder="자재그룹을 선택하세요 (여러 개 선택 가능)"
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
                            st.metric(f"{grp} (kg)", f"{last_val:,.1f}")
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

        # ── 계산 시작 ────────────────────────────────────────────────────
        if selected_groups and selected_packing != "선택하세요":

            st.markdown("#### 📊 시뮬레이션 결과")

            # 슬리브 안내
            if "슬리브" in selected_packing:
                st.info("ℹ️ 슬리브 항목은 현재 파렛트 포장으로 변경 중인 항목입니다.")

            # ── 그룹별 개별 결과 테이블 ─────────────────────────────────
            import math as _math
            if len(selected_groups) > 1:
                st.markdown("**그룹별 계산**")
                rows = []
                total_boxes   = 0.0
                total_pallets = 0.0
                for grp in selected_groups:
                    gw        = group_weights.get(grp, 0.0)
                    box_limit = GROUP_PALLET_LIMIT.get(grp, 20)
                    # ★ 자재그룹별 실제 단위 중량 DB에서 조회
                    unit_w = (PACKING_TABLE.get(selected_packing, {}).get(grp)
                              or PACKING_TABLE.get(selected_packing, {}).get(list(PACKING_TABLE.get(selected_packing, {}).keys())[0] if PACKING_TABLE.get(selected_packing) else None))
                    if not unit_w:
                        st.warning(f"⚠️ {grp} × {selected_packing} 조합의 중량 데이터가 없습니다.")
                        continue
                    g_boxes   = _math.ceil(gw / unit_w) if unit_w else 0
                    g_pallets = _math.ceil(g_boxes / box_limit) if box_limit else 0
                    total_boxes   += g_boxes
                    total_pallets += g_pallets
                    rows.append({
                        "자재그룹": grp,
                        "중량(kg)": f"{gw:,.1f}",
                        "박스당(kg)": f"{unit_w}",
                        "박스(PKG)": f"{g_boxes}",
                        "PLT": f"{g_pallets}",
                        "PLT당 박스": str(box_limit)
                    })
                rows.append({
                    "자재그룹": "✅ 합계",
                    "중량(kg)": f"{sum(group_weights.values()):,.1f}",
                    "박스당(kg)": "",
                    "박스(PKG)": f"{int(total_boxes)}",
                    "PLT": f"{int(total_pallets)}",
                    "PLT당 박스": ""
                })
                import pandas as _pd
                st.dataframe(
                    _pd.DataFrame(rows),
                    use_container_width=True,
                    hide_index=True
                )
                calc_boxes   = total_boxes
                calc_pallets = total_pallets

            else:
                # 단일 그룹
                grp       = selected_groups[0]
                box_limit = GROUP_PALLET_LIMIT.get(grp, 20)
                # ★ 자재그룹별 실제 단위 중량 DB에서 조회
                unit_w = PACKING_TABLE.get(selected_packing, {}).get(grp)
                if not unit_w:
                    st.warning(f"⚠️ {grp} × {selected_packing} 조합의 중량 데이터가 없습니다.")
                    unit_w = 1
                calc_boxes   = _math.ceil(total_target_weight / unit_w)
                calc_pallets = _math.ceil(calc_boxes / box_limit)

                res_col1, res_col2 = st.columns(2)
                with res_col1:
                    st.metric("필요 박스", f"{calc_boxes} PKG")
                with res_col2:
                    st.metric("필요 PLT", f"{calc_pallets} PLT")
                st.caption(f"ℹ️ 적용 기준: {grp} × {selected_packing} = {unit_w}kg/박스 / PLT당 {box_limit}박스")

            # ── 합산 요약 (복수 그룹일 때만) ─────────────────────────────
            if len(selected_groups) > 1:
                col1, col2, col3 = st.columns(3)
                col1.metric("총 박스", f"{int(calc_boxes)} PKG")
                col2.metric("총 PLT",  f"{int(calc_pallets)} PLT")
                col3.metric("포장재", selected_packing)

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
            if st.button("📋 시뮬레이터 문의하기", use_container_width=True):
                grp_summary = ", ".join(f"{g}({group_weights.get(g,0):,.0f}kg)" for g in selected_groups)
                sim_summary = (
                    f"포장재: {selected_packing}\n"
                    f"자재그룹: {grp_summary}\n"
                    f"목표 중량: {total_target_weight:,.0f}kg\n"
                    f"계산 결과: {int(calc_boxes)}박스 / {int(calc_pallets)}PLT"
                )
                show_simulator_inquiry_popup("수출 포장량 시뮬레이터", sim_summary)
        else:
            st.info("자재그룹과 포장재를 선택하시면 시뮬레이션이 시작됩니다.")

    elif current_team == "국내영업팀":
        st.subheader("🚚 국내 최적 운임 비교", divider="rainbow")

        # ── 노선 데이터 로드 ───────────────────────────────────────────────
        @st.cache_data(ttl=300)
        def load_route_data():
            """V3 기준: 시트명='차량 노선 데이터', 도착지='부산(경남권)' 형식"""
            SHEET = "차량 노선 데이터"
            # 1순위: 실제 운영 경로
            search_paths = (
                glob.glob("data/source_docs/*V3*.xlsx") +
                glob.glob("data/source_docs/*.xlsx") +
                glob.glob("/mnt/user-data/uploads/*V3*.xlsx") +
                glob.glob("/mnt/user-data/uploads/*.xlsx")
            )
            df = None
            for path in search_paths:
                try:
                    xf = pd.ExcelFile(path)
                    # 시트명 자동 탐지 (노선 관련)
                    route_sheet = next(
                        (s for s in xf.sheet_names if "노선" in s),
                        None
                    )
                    if route_sheet:
                        df = pd.read_excel(path, sheet_name=route_sheet).fillna("")
                        break
                except Exception:
                    continue
            if df is None:
                return set(), set()

            short_set = set(df[df["거리 기준"] == "단거리"]["도착지"].str.strip().tolist())
            long_set  = set(df[df["거리 기준"] == "장거리"]["도착지"].str.strip().tolist())
            return short_set, long_set

        import glob as glob  # 함수 안에서도 사용 가능하도록
        SHORT_DEST, LONG_DEST = load_route_data()

        # ── 지역 → 구간 분류 (3구간) ─────────────────────────────────────
        # 구간 A: 녹산/대저/명지/경남권  → 300kg 기준
        # 구간 B: 부산시내              → 150kg 기준
        # 구간 C: 이외 장거리           → 800kg 기준
        ZONE_A_KEYWORDS = ["녹산", "대저", "명지", "경남", "양산", "창원", "마산", "진주", "거제", "통영", "사천", "밀양", "함안", "거창", "합천", "의령", "남해", "하동", "산청", "함양", "고성", "창녕"]
        ZONE_B_KEYWORDS = ["부산", "해운대", "동래", "사상", "사하", "강서", "금정", "북구", "동구", "서구", "중구", "영도", "연제", "수영", "남구", "기장"]

        def classify_zone(dest: str):
            """
            입력 도착지 → (zone, threshold, label) 반환
            zone A: 녹산/대저/명지/경남권 — 300kg
            zone B: 부산시내              — 150kg
            zone C: 장거리                — 800kg
            """
            dest_lower = dest.strip()
            # Zone A 우선 (경남권 키워드)
            for kw in ZONE_A_KEYWORDS:
                if kw in dest_lower:
                    return "A", 300, "녹산·대저·명지·경남권"
            # Zone B (부산 키워드) — 단, 경남 이미 매칭된 경우 제외
            for kw in ZONE_B_KEYWORDS:
                if kw in dest_lower:
                    return "B", 150, "부산시내"
            # Zone C: DB 장거리 or 기본 장거리
            return "C", 800, "장거리"

        # ── 입력 폼 ────────────────────────────────────────────────────────
        with st.container(border=True):
            destination  = st.text_input("📍 도착 지역", placeholder="예: 부산, 창원, 서울, 광주")
            total_weight = st.number_input("⚖️ 총 중량 (kg)", min_value=1, value=100)

        # ── 분석 ───────────────────────────────────────────────────────────
        if destination:
            zone, threshold, zone_label = classify_zone(destination)
            is_direct = total_weight > threshold
            best_option = "직송" if is_direct else "화물/택배"

            # ── 결과 UI ───────────────────────────────────────────────────
            # 색상 팔레트
            if is_direct:
                accent      = "#2563eb"   # 파랑 — 직송
                accent_light= "#dbeafe"
                result_icon = "🚛"
            else:
                accent      = "#16a34a"   # 초록 — 화물/택배
                accent_light= "#dcfce7"
                result_icon = "📦"

            zone_colors = {"A": ("#f59e0b", "#fef3c7"), "B": ("#8b5cf6", "#ede9fe"), "C": ("#64748b", "#f1f5f9")}
            zc, zc_light = zone_colors[zone]

            st.markdown(f"""
<style>
.fare-result-wrap{{margin-top:4px;}}
.fare-hero{{
  background:linear-gradient(135deg,{accent}ee,{accent}bb);
  border-radius:14px;padding:16px 18px;margin-bottom:10px;
  display:flex;align-items:center;gap:12px;
}}
.fare-hero-icon{{font-size:28px;line-height:1;}}
.fare-hero-text{{color:#fff;}}
.fare-hero-label{{font-size:11px;opacity:.85;letter-spacing:.5px;text-transform:uppercase;}}
.fare-hero-value{{font-size:22px;font-weight:800;line-height:1.2;}}
.fare-row{{display:flex;gap:8px;margin-bottom:8px;}}
.fare-chip{{
  flex:1;border-radius:10px;padding:10px 12px;
  background:var(--secondary-background-color);
}}
.fare-chip-label{{font-size:11px;color:#888;margin-bottom:3px;}}
.fare-chip-value{{font-size:14px;font-weight:700;}}
.fare-zone-badge{{
  display:inline-block;padding:2px 10px;border-radius:20px;
  font-size:11px;font-weight:700;
  background:{zc_light};color:{zc};
}}
.fare-divider{{border:none;border-top:1px solid var(--secondary-background-color);margin:10px 0;}}
</style>
<div class="fare-result-wrap">
  <div class="fare-hero">
    <div class="fare-hero-icon">{result_icon}</div>
    <div class="fare-hero-text">
      <div class="fare-hero-label">추천 운임 방법</div>
      <div class="fare-hero-value">{best_option}</div>
    </div>
  </div>
  <div class="fare-row">
    <div class="fare-chip">
      <div class="fare-chip-label">도착 지역</div>
      <div class="fare-chip-value">{destination} <span class="fare-zone-badge">{zone_label}</span></div>
    </div>
  </div>
  <div class="fare-row">
    <div class="fare-chip">
      <div class="fare-chip-label">총 중량</div>
      <div class="fare-chip-value">{total_weight:,} kg</div>
    </div>
    <div class="fare-chip">
      <div class="fare-chip-label">판단 기준</div>
      <div class="fare-chip-value">{threshold:,} kg {'초과 → 직송' if is_direct else '이하 → 화물/택배'}</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

            # 기준표 expander — 3구간 카드
            with st.expander("📋 운임 선택 기준 전체 보기"):
                st.markdown(f"""
<style>
.zone-card{{border-radius:10px;padding:11px 14px;margin-bottom:8px;border-left:4px solid;background:var(--secondary-background-color);}}
.zone-a{{border-color:#f59e0b;}}
.zone-b{{border-color:#8b5cf6;}}
.zone-c{{border-color:#64748b;}}
.zone-title{{font-size:12px;font-weight:700;margin-bottom:5px;color:var(--text-color);}}
.zone-row{{font-size:12px;line-height:1.8;color:var(--text-color);}}
.tag{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:700;}}
.tag-d{{background:rgba(37,99,235,0.15);color:#2563eb;border:1px solid rgba(37,99,235,0.3);}}
.tag-c{{background:rgba(22,163,74,0.15);color:#16a34a;border:1px solid rgba(22,163,74,0.3);}}
</style>
<div class="zone-card zone-a">
  <div class="zone-title">🟡 녹산·대저·명지·경남권</div>
  <div class="zone-row">
    300 kg 이하 → <span class="tag tag-c">화물/택배</span><br>
    300 kg 초과 → <span class="tag tag-d">직송</span>
  </div>
</div>
<div class="zone-card zone-b">
  <div class="zone-title">🟣 부산시내</div>
  <div class="zone-row">
    150 kg 이하 → <span class="tag tag-c">화물/택배</span><br>
    150 kg 초과 → <span class="tag tag-d">직송</span>
  </div>
</div>
<div class="zone-card zone-c">
  <div class="zone-title">⚫ 이외 장거리</div>
  <div class="zone-row">
    800 kg 이하 → <span class="tag tag-c">화물/택배</span><br>
    800 kg 초과 → <span class="tag tag-d">직송</span>
  </div>
</div>
<div style="font-size:11px;color:#999;margin-top:4px;">※ 기준: 물류팀 운영 규칙</div>
""", unsafe_allow_html=True)

            if st.button("📋 시뮬레이터 문의하기", use_container_width=True):
                sim_summary = (
                    f"도착지: {destination} ({zone_label})\n"
                    f"총 중량: {total_weight:,}kg\n"
                    f"기준 중량: {threshold:,}kg\n"
                    f"추천 운송 방식: {best_option}"
                )
                show_simulator_inquiry_popup("국내 최적 운임 비교", sim_summary)

        # ── 국내 최적 배차 시뮬레이터 (국내영업팀 전용) ─────────────────────
        st.markdown("---")
        st.subheader("🚛 최적 배차 시뮬레이터", divider="rainbow")

        with st.container(border=True):
            dom_item_code = st.text_input(
                "🔖 자재코드", placeholder="예: 6004216", key="dom_item_code"
            ).strip().split(".")[0].strip()
            dom_qty = st.number_input("📦 수량 (PC)", min_value=1, value=1, key="dom_qty")

        if dom_item_code:
            # 크롤러 데이터 로드 (load_crawler_data 재사용)
            @st.cache_data(ttl=300)
            def load_crawler_data_dom():
                import glob as _glob
                CRAWLER_SHEET_KEYWORD = "크롤러"
                search_paths = (
                    _glob.glob("data/source_docs/*V4*.xlsx") +
                    _glob.glob("data/source_docs/*V3*.xlsx") +
                    _glob.glob("data/source_docs/*.xlsx") +
                    _glob.glob("/mnt/user-data/uploads/*V4*.xlsx") +
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
                weight_col = find_col("중량") or find_col("KG") or find_col("kg")  # ★ 중량 탐지
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
                        "weight_per_pc": weight_per_pc,   # ★ kg/PC
                    }
                return data

            DOM_CRAWLER_DATA = load_crawler_data_dom()
            item = DOM_CRAWLER_DATA.get(dom_item_code)

            if not item:
                partials = [c for c in DOM_CRAWLER_DATA if dom_item_code in c]
                if partials:
                    st.warning(f"정확한 코드를 찾지 못했습니다. 유사 코드: {', '.join(partials[:5])}")
                else:
                    st.error("❌ 등록되지 않은 자재코드입니다. DB를 확인해주세요.")
            else:
                st.markdown(f"**자재내역:** `{item['name']}`")

                max_pc        = item['max_pc']
                need_plt      = dom_qty / max_pc
                need_plt_ceil = -(-dom_qty // max_pc)

                # ★ 총 중량 계산
                weight_per_pc   = item.get('weight_per_pc')
                total_weight_kg = (weight_per_pc * dom_qty) if weight_per_pc else 0.0

                st.markdown("#### 📊 적재 계산")
                st.markdown(f"""
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px;">
  <div style="flex:1 1 90px;min-width:90px;background:var(--secondary-background-color);
       border-radius:10px;padding:12px 14px;text-align:center;">
    <div style="font-size:13px;color:var(--text-color);opacity:0.6;margin-bottom:4px;">수량</div>
    <div style="font-size:20px;font-weight:700;color:var(--text-color);">{dom_qty} PC</div>
  </div>
  <div style="flex:1 1 90px;min-width:90px;background:var(--secondary-background-color);
       border-radius:10px;padding:12px 14px;text-align:center;">
    <div style="font-size:13px;color:var(--text-color);opacity:0.6;margin-bottom:4px;">PLT당 최대</div>
    <div style="font-size:20px;font-weight:700;color:var(--text-color);">{max_pc} PC</div>
  </div>
  <div style="flex:1 1 90px;min-width:90px;background:var(--secondary-background-color);
       border-radius:10px;padding:12px 14px;text-align:center;">
    <div style="font-size:13px;color:var(--text-color);opacity:0.6;margin-bottom:4px;">필요 파렛트</div>
    <div style="font-size:20px;font-weight:700;color:var(--text-color);">{need_plt_ceil} PLT</div>
  </div>
</div>
""", unsafe_allow_html=True)

                if weight_per_pc:
                    st.markdown(f"""
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px;">
  <div style="flex:1 1 90px;min-width:90px;background:var(--secondary-background-color);
       border-radius:10px;padding:12px 14px;text-align:center;">
    <div style="font-size:13px;color:var(--text-color);opacity:0.6;margin-bottom:4px;">1PC당 중량</div>
    <div style="font-size:20px;font-weight:700;color:var(--text-color);">{weight_per_pc:,.1f} kg</div>
  </div>
  <div style="flex:1 1 90px;min-width:90px;background:var(--secondary-background-color);
       border-radius:10px;padding:12px 14px;text-align:center;">
    <div style="font-size:13px;color:var(--text-color);opacity:0.6;margin-bottom:4px;">총 중량</div>
    <div style="font-size:20px;font-weight:700;color:var(--text-color);">{total_weight_kg:,.0f} kg</div>
    <div style="font-size:13px;color:var(--text-color);opacity:0.55;margin-top:3px;">({total_weight_kg/1000:.2f} ton)</div>
  </div>
</div>
""", unsafe_allow_html=True)

                st.caption(
                    f"파렛트 사이즈: {int(item['plt_w']*1000)} × {int(item['plt_l']*1000)} mm  |  "
                    f"계산: {dom_qty} ÷ {max_pc} = {need_plt:.2f} → 올림 {need_plt_ceil} PLT"
                )

                best_truck = get_db_transport_advice(
                    need_plt_ceil, total_weight_kg,
                    plt_w=item['plt_w'], plt_l=item['plt_l']
                )
                with st.expander("🚚 최적 배차 추천", expanded=True):
                    render_truck_advice(best_truck, need_plt_ceil, total_weight_kg,
                                        weight_per_pc, key_prefix="dom")

                if st.button("📋 시뮬레이터 문의하기", use_container_width=True, key="dom_truck_query"):
                    truck_name = best_truck['name'] if best_truck else "없음"
                    weight_line = f"\n총 중량: {total_weight_kg:,.0f}kg ({total_weight_kg/1000:.2f}ton)" if weight_per_pc else ""
                    sim_summary = (
                        f"자재코드: {dom_item_code} ({item['name']})\n"
                        f"수량: {dom_qty}PC → {need_plt_ceil}PLT{weight_line}\n"
                        f"추천 차량: {truck_name}"
                    )
                    show_simulator_inquiry_popup("국내 최적 배차 시뮬레이터", sim_summary)
        else:
            st.info("자재코드와 수량을 입력하시면 DB 기반으로 최적 차량을 분석합니다.")


    elif current_team == "트랙영업팀":
        st.subheader("🚜 크롤러 배차 시뮬레이터", divider="rainbow")

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
            import glob as _glob

            CRAWLER_SHEET_KEYWORD = "크롤러"

            search_paths = (
                _glob.glob("data/source_docs/*V3*.xlsx") +
                _glob.glob("data/source_docs/*.xlsx") +
                _glob.glob("/mnt/user-data/uploads/*V3*.xlsx") +
                _glob.glob("/mnt/user-data/uploads/*.xlsx")
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
                    # 0행이 섹션 제목인지 확인해서 header 자동 결정
                    df_test = pd.read_excel(path, sheet_name=crawler_sheet, header=0, nrows=2)
                    first_col = str(df_test.columns[0])
                    # 첫 컬럼이 '[크롤러...]' 같은 섹션 제목이면 header=1
                    if first_col.startswith("[") or "Unnamed" in first_col:
                        df = pd.read_excel(path, sheet_name=crawler_sheet, header=1).fillna("")
                    else:
                        df = pd.read_excel(path, sheet_name=crawler_sheet, header=0).fillna("")
                    break
                except Exception:
                    continue

            if df is None:
                return {}

            # 컬럼명 자동 탐지 (이름이 바뀌어도 키워드로 찾기)
            cols = df.columns.tolist()
            def find_col(kw):
                return next((c for c in cols if kw in str(c)), None)

            code_col   = find_col("자재코드")
            name_col   = find_col("자재내역")
            qty_col    = find_col("최대 적재 수량") or find_col("적재 수량")
            size_col   = find_col("사이즈")
            weight_col = find_col("중량") or find_col("KG") or find_col("kg")  # ★ 중량 컬럼 탐지

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
                # ★ 1PC당 중량(kg) 파싱
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
                    "weight_per_pc": weight_per_pc,   # ★ kg/PC (없으면 None)
                }
            return data

        CRAWLER_DATA = load_crawler_data()

        # ── 입력 폼 ────────────────────────────────────────────────────────
        with st.container(border=True):
            t_item_code = st.text_input(
                "🔖 자재코드", placeholder="예: 6004216"
            ).strip().split(".")[0].strip()
            t_qty = st.number_input("📦 수량 (PC)", min_value=1, value=1)

        # ── 계산 ───────────────────────────────────────────────────────────
        if t_item_code:
            item = CRAWLER_DATA.get(t_item_code)
            if not item:
                # 부분 일치 검색
                partials = [c for c in CRAWLER_DATA if t_item_code in c]
                if partials:
                    st.warning(f"정확한 코드를 찾지 못했습니다. 유사 코드: {', '.join(partials[:5])}")
                else:
                    st.error("❌ 등록되지 않은 자재코드입니다. DB를 확인해주세요.")
            else:
                st.markdown(f"**자재내역:** `{item['name']}`")

                # 파렛트 수 계산
                max_pc        = item['max_pc']
                need_plt      = t_qty / max_pc
                need_plt_ceil = -(-t_qty // max_pc)

                # ★ 총 중량 계산
                weight_per_pc  = item.get('weight_per_pc')
                total_weight_kg = (weight_per_pc * t_qty) if weight_per_pc else 0.0

                st.markdown("#### 📊 적재 계산")
                st.markdown(f"""
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px;">
  <div style="flex:1 1 90px;min-width:90px;background:var(--secondary-background-color);
       border-radius:10px;padding:12px 14px;text-align:center;">
    <div style="font-size:13px;color:var(--text-color);opacity:0.6;margin-bottom:4px;">수량</div>
    <div style="font-size:20px;font-weight:700;color:var(--text-color);">{t_qty} PC</div>
  </div>
  <div style="flex:1 1 90px;min-width:90px;background:var(--secondary-background-color);
       border-radius:10px;padding:12px 14px;text-align:center;">
    <div style="font-size:13px;color:var(--text-color);opacity:0.6;margin-bottom:4px;">PLT당 최대</div>
    <div style="font-size:20px;font-weight:700;color:var(--text-color);">{max_pc} PC</div>
  </div>
  <div style="flex:1 1 90px;min-width:90px;background:var(--secondary-background-color);
       border-radius:10px;padding:12px 14px;text-align:center;">
    <div style="font-size:13px;color:var(--text-color);opacity:0.6;margin-bottom:4px;">필요 파렛트</div>
    <div style="font-size:20px;font-weight:700;color:var(--text-color);">{need_plt_ceil} PLT</div>
  </div>
</div>
""", unsafe_allow_html=True)

                if weight_per_pc:
                    st.markdown(f"""
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px;">
  <div style="flex:1 1 90px;min-width:90px;background:var(--secondary-background-color);
       border-radius:10px;padding:12px 14px;text-align:center;">
    <div style="font-size:13px;color:var(--text-color);opacity:0.6;margin-bottom:4px;">1PC당 중량</div>
    <div style="font-size:20px;font-weight:700;color:var(--text-color);">{weight_per_pc:,.1f} kg</div>
  </div>
  <div style="flex:1 1 90px;min-width:90px;background:var(--secondary-background-color);
       border-radius:10px;padding:12px 14px;text-align:center;">
    <div style="font-size:13px;color:var(--text-color);opacity:0.6;margin-bottom:4px;">총 중량</div>
    <div style="font-size:20px;font-weight:700;color:var(--text-color);">{total_weight_kg:,.0f} kg</div>
    <div style="font-size:13px;color:var(--text-color);opacity:0.55;margin-top:3px;">({total_weight_kg/1000:.2f} ton)</div>
  </div>
</div>
""", unsafe_allow_html=True)

                st.caption(
                    f"파렛트 사이즈: {int(item['plt_w']*1000)} × {int(item['plt_l']*1000)} mm  |  "
                    f"계산: {t_qty} ÷ {max_pc} = {need_plt:.2f} → 올림 {need_plt_ceil} PLT"
                )

                best_truck = get_db_transport_advice(
                    need_plt_ceil, total_weight_kg,
                    plt_w=item['plt_w'], plt_l=item['plt_l']
                )
                with st.expander("🚚 최적 배차 추천", expanded=True):
                    render_truck_advice(best_truck, need_plt_ceil, total_weight_kg,
                                        weight_per_pc, key_prefix="trk")

                if st.button("📋 시뮬레이터 문의하기", use_container_width=True):
                    truck_name = best_truck['name'] if best_truck else "없음"
                    weight_line = f"\n총 중량: {total_weight_kg:,.0f}kg ({total_weight_kg/1000:.2f}ton)" if weight_per_pc else ""
                    sim_summary = (
                        f"자재코드: {t_item_code} ({item['name']})\n"
                        f"수량: {t_qty}PC → {need_plt_ceil}PLT{weight_line}\n"
                        f"추천 차량: {truck_name}"
                    )
                    show_simulator_inquiry_popup("크롤러 배차 시뮬레이터", sim_summary)
        else:
            st.info("자재코드와 수량을 입력하시면 DB 기반으로 최적 차량을 분석합니다.")
                       
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
                if not improve_text.strip():
                    st.warning("내용을 입력해주세요.")
                else:
                    current_team_for_mail = st.session_state.get("selected_team", "전체")
                    try:
                        success = EMAIL_NOTIFIER.send_improvement_request(
                            content=improve_text.strip(),
                            team=current_team_for_mail
                        )
                    except Exception:
                        success = False
                    st.session_state.improve_submitted = True
                    st.session_state.show_improve_form = False
                    if success:
                        st.toast("✅ 개선 요청이 담당자에게 전달되었습니다!", icon="💡")
                    else:
                        st.toast("⚠️ 전송에 실패했습니다. 직접 담당자에게 문의해주세요.", icon="⚠️")
                    st.rerun()
        with _cancel_col:
            if st.button("✖ 취소", use_container_width=True, key="cancel_improve"):
                st.session_state.show_improve_form = False
                st.rerun()

st.title("📦 DRB LOGIBOT-AI")
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
    clean_content = re.sub(r'\s?\d\.\d{3}\s?', '', msg["content"]).strip()

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
                            []
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