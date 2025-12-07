import streamlit as st
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from rag_pipeline.query_processor import get_rag_response, submit_feedback
load_dotenv()

# ---------- 초기 설정 ----------
st.set_page_config(page_title="물류 AI 챗봇 (RAG)", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    .stApp {
        background-color: #0f1720;
        color: #e6eef8;
    }
    .app-logo {
        position: fixed;
        top: 10px;
        left: 18px;
        z-index: 999;
        font-weight: 800;
        font-size: 20px;
        color: #ff4d4f;
        letter-spacing: 2px;
    }
    .chat-container {
        padding-top: 48px;
    }
    .chat-bubble {
        max-width: 78%;
        padding: 12px 14px;
        border-radius: 14px;
        margin-bottom: 8px;
        line-height: 1.4;
        font-size: 14px;
    }
    .chat-bubble.user {
        background: linear-gradient(90deg, rgba(38,99,255,0.12), rgba(38,99,255,0.08));
        color: #dbeafe;
        border-top-right-radius: 4px;
        margin-left: auto;
        text-align: left;
    }
    .chat-bubble.assistant {
        background: rgba(255,255,255,0.03);
        color: #e6eef8;
        border-top-left-radius: 4px;
        margin-right: auto;
        text-align: left;
    }
    .conversation-item {
        padding: 10px;
        margin: 5px 0;
        background: rgba(255,255,255,0.05);
        border-radius: 8px;
        cursor: pointer;
        transition: background 0.2s;
    }
    .conversation-item:hover {
        background: rgba(255,255,255,0.1);
    }
    .conversation-title {
        font-size: 14px;
        font-weight: 600;
        color: #e6eef8;
        margin-bottom: 4px;
    }
    .conversation-date {
        font-size: 11px;
        color: #888;
    }
    .active-conversation {
        background: rgba(38,99,255,0.15);
        border-left: 3px solid #2663ff;
    }
    .css-1d391kg {
        padding-top: 52px;
    }
    .stButton>button {
        border-radius: 8px;
        width: 100%;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown('<div class="app-logo">DRB</div>', unsafe_allow_html=True)
st.title("📦DRB LOGIBOT-AI (물류팀 챗봇)")

# ---------- 세션 상태 초기화 ----------
if "conversations" not in st.session_state:
    st.session_state["conversations"] = {}

if "current_conversation_id" not in st.session_state:
    new_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state["current_conversation_id"] = new_id
    st.session_state["conversations"][new_id] = {
        "title": "새 대화",
        "created_at": datetime.now().isoformat(),
        "messages": [{"role": "assistant", "content": "안녕하세요! 궁금한 점을 질문해 주세요."}]
    }

if "system_prompt" not in st.session_state:
    st.session_state["system_prompt"] = """당신은 물류 업무 전문가입니다. 

    답변 시 다음 형식을 따르세요:
    1. 핵심 요약을 먼저 2-3줄로 작성
    2. 세부 내용은 번호를 매겨 구조화
    3. 절차나 프로세스는 단계별로 명확히 구분
    4. 특수문자(**, ###, 등)는 사용하지 마세요
    5. 답변은 실무에 바로 적용 가능하도록 구체적으로 작성

    간결하지만 핵심을 놓치지 않는 답변을 제공하세요."""

if "feedback_submitted" not in st.session_state:
    st.session_state["feedback_submitted"] = set()

if "rename_mode" not in st.session_state:
    st.session_state["rename_mode"] = None

# ✅ 개선: 각 메시지에 대한 sources 저장
if "message_sources" not in st.session_state:
    st.session_state["message_sources"] = {}

# ---------- 헬퍼 함수 ----------
def get_current_messages():
    """현재 대화의 메시지 리스트 반환"""
    conv_id = st.session_state["current_conversation_id"]
    return st.session_state["conversations"][conv_id]["messages"]

def add_message(role, content, sources=None):
    """현재 대화에 메시지 추가"""
    conv_id = st.session_state["current_conversation_id"]
    msg_index = len(st.session_state["conversations"][conv_id]["messages"])
    
    st.session_state["conversations"][conv_id]["messages"].append({
        "role": role,
        "content": content
    })
    
    # ✅ sources 정보 저장
    if sources is not None:
        st.session_state["message_sources"][f"{conv_id}_{msg_index}"] = sources
    
    # 첫 메시지인 경우 대화 제목 업데이트
    if len(st.session_state["conversations"][conv_id]["messages"]) == 2:
        title = content[:30] + "..." if len(content) > 30 else content
        st.session_state["conversations"][conv_id]["title"] = title

def get_message_sources(msg_index):
    """특정 메시지의 sources 조회"""
    conv_id = st.session_state["current_conversation_id"]
    return st.session_state["message_sources"].get(f"{conv_id}_{msg_index}", [])

def create_new_conversation():
    """새 대화 생성"""
    new_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state["current_conversation_id"] = new_id
    st.session_state["conversations"][new_id] = {
        "title": "새 대화",
        "created_at": datetime.now().isoformat(),
        "messages": [{"role": "assistant", "content": "안녕하세요! 궁금한 점을 질문해 주세요."}]
    }

def switch_conversation(conv_id):
    """다른 대화로 전환"""
    st.session_state["current_conversation_id"] = conv_id
    st.session_state["rename_mode"] = None

def delete_current_conversation():
    """현재 대화 삭제"""
    conv_id = st.session_state["current_conversation_id"]
    if len(st.session_state["conversations"]) > 1:
        del st.session_state["conversations"][conv_id]
        remaining_ids = sorted(st.session_state["conversations"].keys(), reverse=True)
        st.session_state["current_conversation_id"] = remaining_ids[0]
    else:
        st.session_state["conversations"][conv_id]["messages"] = [
            {"role": "assistant", "content": "안녕하세요! 궁금한 점을 질문해 주세요."}
        ]
        st.session_state["conversations"][conv_id]["title"] = "새 대화"
    st.session_state["rename_mode"] = None

def rename_conversation(conv_id, new_title):
    """대화 제목 변경"""
    if new_title.strip():
        st.session_state["conversations"][conv_id]["title"] = new_title.strip()
    st.session_state["rename_mode"] = None

# ---------- 사이드바 (대화 목록) ----------
with st.sidebar:
    st.header("💬 대화 목록")
    
    if st.button("새 대화 시작", use_container_width=True):
        create_new_conversation()
        st.rerun()
    
    st.markdown("---")
    
    sorted_convs = sorted(
        st.session_state["conversations"].items(),
        key=lambda x: x[1]["created_at"],
        reverse=True
    )
    
    for conv_id, conv_data in sorted_convs:
        is_active = conv_id == st.session_state["current_conversation_id"]
        
        if st.session_state["rename_mode"] == conv_id:
            new_title = st.text_input(
                "새 제목",
                value=conv_data["title"],
                key=f"rename_input_{conv_id}",
                label_visibility="collapsed"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 확인", key=f"confirm_{conv_id}", use_container_width=True):
                    rename_conversation(conv_id, new_title)
                    st.rerun()
            with col2:
                if st.button("❌ 취소", key=f"cancel_{conv_id}", use_container_width=True):
                    st.session_state["rename_mode"] = None
                    st.rerun()
        else:
            button_label = f"{'🟢 ' if is_active else '⚪ '}{conv_data['title']}"
            
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                if st.button(button_label, key=f"conv_{conv_id}", use_container_width=True):
                    if not is_active:
                        switch_conversation(conv_id)
                        st.rerun()
            
            with col2:
                if is_active:
                    if st.button("✏️", key=f"edit_{conv_id}"):
                        st.session_state["rename_mode"] = conv_id
                        st.rerun()
            
            with col3:
                if is_active:
                    if st.button("🗑️", key=f"del_{conv_id}"):
                        delete_current_conversation()
                        st.rerun()
            
            created_dt = datetime.fromisoformat(conv_data["created_at"])
            st.caption(created_dt.strftime("%m/%d %H:%M"))
        
        if conv_id != sorted_convs[-1][0]:
            st.markdown("---") 
    
    st.markdown("---")
    
    if st.button("현재 대화 내보내기", use_container_width=True):
        conv_id = st.session_state["current_conversation_id"]
        conv_data = st.session_state["conversations"][conv_id]
        payload = json.dumps(conv_data, ensure_ascii=False, indent=2)
        st.download_button(
            "다운로드 JSON",
            data=payload,
            file_name=f"conversation_{conv_id}.json",
            mime="application/json",
            use_container_width=True
        )

# ---------- 메인: 채팅 영역 ----------
col1, col2 = st.columns([3, 1])

with col1:
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)

    messages = get_current_messages()
    
    for idx, msg in enumerate(messages):
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        
        if role == "user":
            st.markdown(f'<div class="chat-bubble user">{content}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-bubble assistant">{content}</div>', unsafe_allow_html=True)
            
            # ✅ 개선: 답변에 대한 피드백 버튼 (sources 포함)
            if idx > 0 and idx not in st.session_state["feedback_submitted"]:
                col1, col2, col3 = st.columns([1, 1, 8])
                
                with col1:
                    if st.button("👍", key=f"good_{idx}"):
                        user_query = messages[idx-1]["content"] if idx > 0 else ""
                        bot_answer = content
                        sources = get_message_sources(idx)  # ✅ sources 조회
                        
                        submit_feedback(user_query, 1.0, bot_answer, sources)
                        st.session_state["feedback_submitted"].add(idx)
                        st.success("피드백 감사합니다! 👍")
                        time.sleep(1)
                        st.rerun()

                with col2:
                    if st.button("👎", key=f"bad_{idx}"):
                        user_query = messages[idx-1]["content"] if idx > 0 else ""
                        bot_answer = content
                        sources = get_message_sources(idx)  # ✅ sources 조회
                        
                        submit_feedback(user_query, 0.0, bot_answer, sources)
                        st.session_state["feedback_submitted"].add(idx)
                        st.warning("피드백 감사합니다. 개선하겠습니다! 👎")
                        time.sleep(1)
                        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    prompt = st.chat_input("메시지를 입력하고 Enter를 누르세요...")

    def call_rag(prompt_text):
        """get_rag_response 호출"""
        try:
            result = get_rag_response(prompt_text)
            if isinstance(result, dict):
                return result.get('answer', str(result)), result.get('sources', [])
            return str(result), []
        except Exception as e:
            return f"응답 생성 중 오류가 발생했습니다: {e}", []

    if prompt:
        add_message("user", prompt)
        st.rerun()

# ---------- 응답 생성 로직 ----------
def need_response():
    messages = get_current_messages()
    if not messages:
        return False
    if messages[-1]["role"] == "user":
        return True
    return False

if need_response():
    messages = get_current_messages()
    user_msg = messages[-1]["content"]
    
    composed_prompt = f"""당신은 물류 전문가입니다.

    답변 형식 요구사항:
    - 핵심 내용을 먼저 1-2줄로 요약
    - 세부 내용은 번호나 bullet point로 구조화
    - 절차는 단계별로 명확히 구분
    - 중요 키워드는 강조

    사용자 질문: {user_msg}

    위 형식을 반드시 지켜서 한국어로 답변해주세요."""
    
    # ✅ 개선: 로딩 메시지
    with st.spinner("🤖 답변 생성 중..."):
        add_message("assistant", "응답 생성 중...")
        
        try:
            result, sources = call_rag(composed_prompt)  # ✅ sources도 받기
            messages = get_current_messages()
            msg_idx = len(messages) - 1
            messages[-1] = {"role": "assistant", "content": result}
            
            # ✅ sources 저장
            conv_id = st.session_state["current_conversation_id"]
            st.session_state["message_sources"][f"{conv_id}_{msg_idx}"] = sources
            
        except Exception as e:
            messages = get_current_messages()
            messages[-1] = {"role": "assistant", "content": f"응답 생성 중 오류가 발생했습니다: {e}"}
    
    st.rerun()