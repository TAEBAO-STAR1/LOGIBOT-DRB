import os
import time
import json
import logging
import requests
import hashlib
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv
from pydantic import PrivateAttr
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.llms import LLM
from langchain_qdrant import Qdrant
from langchain_ollama import OllamaEmbeddings 
from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from ddgs import DDGS
from functools import lru_cache
import threading
import pandas as pd
import fitz

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# 환경 변수
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "logistics_data")
QDRANT_HOST = os.getenv("QDRANT_HOST", "http://localhost:6333")
LEARNING_COLLECTION = os.getenv("LEARNING_COLLECTION", "learning_history")
BAD_FEEDBACK_COLLECTION = os.getenv("BAD_FEEDBACK_COLLECTION", "bad_feedback_history")

# 이메일 설정 (환경 변수에서 가져오기)
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USERNAME)
EMAIL_TO = os.getenv("EMAIL_TO", "").split(",")  # 쉼표로 구분된 수신자 목록

# 로깅 전용 컬렉션
QUERY_LOG_COLLECTION = "query_logs"
ANSWER_LOG_COLLECTION = "answer_logs"

ONPREMISE_API_URL = os.getenv("ONPREMISE_API_URL", "http://192.168.1.121:11436/v1/chat/completions")
ONPREMISE_MODEL = os.getenv("ONPREMISE_MODEL", "ISTA-DASLab/gemma-3-27b-it-GPTQ-4b-128g")
ONPREMISE_TIMEOUT = int(os.getenv("ONPREMISE_TIMEOUT", "60"))
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "granite-embedding:278m")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# 캐시 설정
CACHE_TTL = 300
response_cache = {}
cache_lock = threading.Lock()

# 개선된 프롬프트
PROMPT_TEMPLATE = """당신은 DRB 물류 전문 AI 어시스턴트입니다.
아래 [참고 데이터]를 바탕으로 사용자의 질문에 답변하세요.

[이전 대화]
{conversation_context}

[과거 유사 답변]
{history_context}

[참고 데이터]
{context}

[질문]
{input}

[답변 작성 규칙]ㅍ
1. **출처 표기 금지**: "문서 1", "[문서 2]" 같은 내부 참조 번호를 절대 답변에 포함하지 마세요.
2. **정보 통합**: 여러 데이터에 걸쳐 있는 정보는 하나로 합쳐서 자연스럽게 설명하세요.
3. **계산 표현 방식**: 계산 과정은 반드시 아래 자연어 형식으로만 작성하세요. LaTeX 수식 문법(행렬, aligned 환경 등)을 절대 사용하지 마세요.
   올바른 예시:
   - 포의 총두께 = (4.8 + 2.4) + (3 × 1.15 - 0.2) = 7.2 + 3.25 = **10.45 mm**
   - 롤 직경 = √(10.45 ÷ 1000 × 4 × 100 ÷ 3.142 + 0.09) = √1.42 ≈ **1.19 m (1190 mm)**
4. **계산 질문**: '몇 박스', '산출', '계산' 키워드가 있으면 공식과 계산 과정을 단계별로 보여주세요.
5. **수량 질문**: '몇 명', '몇 개', '전체' 등의 질문은 데이터를 빠짐없이 세어 정확한 합계를 제시하세요.
6. **표 활용**: 비교/목록 데이터는 Markdown 표로 정리하세요.
7. **없는 정보**: 참고 데이터에 없는 내용은 "해당 정보를 찾을 수 없습니다"라고 솔직하게 말하세요.
8. **간결하고 명확하게**: 불필요한 서론 없이 핵심 답변부터 시작하세요.
9. **배차 계산 절차**: '몇 톤', '배차', '차량'이 포함된 질문은 반드시 아래 순서로 답변하세요.
   ① 자재코드로 1파렛트당 최대 적재 수량(PC) 확인
   ② 총 수량 ÷ 1파렛트당 수량 = 필요 파렛트 수 계산
   ③ 파렛트 사이즈(가로×세로)와 차량 적재함 폭·길이를 비교
   ④ 조건을 충족하는 가장 작은 차량 추천 (차량 데이터 참고)
10. **컨베어벨트 직경 계산 절차**: '직경', '롤 직경', 'Roll Dia' 관련 질문은 아래 순서로 답변하세요.
    ① 자재코드로 상고무두께, 하고무두께, 심체수(PLY), 코팅후 포두께 값 확인
    ② 포의 총두께 = (상고무두께 + 하고무두께) + (PLY × 코팅후 포두께 - 0.2)  ← 자연어로 숫자 대입해서 계산
    ③ 롤 직경(m) = √(포의 총두께 ÷ 1000 × 4 × 컨베어벨트 길이(M) ÷ 3.142 + 0.09)
    ④ 컨베어벨트 길이(M)가 질문에 없으면 계산 과정 ①②를 먼저 보여주고,
       "롤 직경 계산을 완성하려면 컨베어벨트 길이(M)를 알려주세요." 라고 요청하세요.
    ⑤ 길이가 주어진 경우 최종 롤 직경(m)과 mm 단위 환산값을 함께 제시하세요.
    
11. **담당자/인원 조회 규칙**: '담당자', '담당', '누구', '연락처', '전화번호', '인원' 등의 키워드가 포함된 질문은
    반드시 [물류팀 현황 데이터]를 우선 참조하여 아래 기준으로 필터링하세요.

    [업무 영역 키워드 매핑]
    - "국내", "내수", "내수출고", "내수담당"  → 담당 공정에 "내수" 포함된 인원
    - "수출", "해외", "수출담당"             → 담당 공정에 "수출" 포함된 인원
    - "입고", "입고담당"                     → 담당 공정에 "입고" 포함된 인원
    - "원자재", "원자재 담당"               → 담당 공정에 "원자재" 포함된 인원
    - "컨베어", "크롤러", "트랙"             → 담당 공정에 "컨베어" 또는 "크롤러" 포함된 인원
    - "중부", "중부물류센터"                 → 담당 공정에 "중부" 포함된 인원
    - "베트남"                              → 담당 공정에 "베트남" 포함된 인원
    - "청도"                                → 담당 공정에 "청도" 포함된 인원
    - "팀장", "총괄"                         → 구분이 팀장이거나 물류팀 총괄 인원
    - "지입기사", "기사", "부산기사"          → 부산공장/중부물류센터 지입기사 인원

    [답변 형식]
    해당 인원을 표 형식으로 정리하세요:
    | 성명 | 직책 | 담당 공정 | 연락처(내선) |
    전화번호가 0인 경우 "직통번호 없음 (내선 문의)"으로 표시하세요.
답변:"""

class EmailNotifier:
    """부정 피드백 이메일 알림 시스템"""
    
    def __init__(self):
        self.enabled = EMAIL_ENABLED
        self.smtp_server = SMTP_SERVER
        self.smtp_port = SMTP_PORT
        self.username = SMTP_USERNAME
        self.password = SMTP_PASSWORD
        self.email_from = EMAIL_FROM
        self.email_to = [email.strip() for email in EMAIL_TO if email.strip()]
        
        if self.enabled:
            if not self.username or not self.password:
                logger.warning("⚠️ 이메일 알림이 활성화되었지만 SMTP 계정 정보가 없습니다.")
                self.enabled = False
            elif not self.email_to:
                logger.warning("⚠️ 이메일 알림이 활성화되었지만 수신자가 지정되지 않았습니다.")
                self.enabled = False
            else:
                logger.info(f"✅ 이메일 알림 활성화: {', '.join(self.email_to)}")
    
    def send_bad_feedback_notification(self, feedback_data: Dict):
        """부정 피드백 발생 시 이메일 전송"""
        if not self.enabled:
            return
        
        try:
            # 이메일 본문 구성
            html_content = self._create_html_email(feedback_data)
            
            # 이메일 메시지 생성
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[물류 AI 챗봇] 부정 피드백 알림 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            # 발신자 표시명만 보이고 실제 계정 주소는 숨김
            from email.utils import formataddr
            msg['From'] = formataddr(("DRB LOGIBOT-AI", self.email_from))
            msg['To'] = ', '.join(self.email_to)
            
            # HTML 파트 추가
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # SMTP 서버 연결 및 전송
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            logger.info(f"✅ 부정 피드백 이메일 전송 완료: {feedback_data['query'][:30]}...")
            
        except Exception as e:
            logger.error(f"❌ 이메일 전송 실패: {e}")

    def send_improvement_request(self, content: str, team: str):
        """개선 요청 이메일 전송"""
        if not self.enabled:
            return False
        try:
            from email.utils import formataddr
            ts = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
            html_content = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<style>
  body {{ font-family: 'Malgun Gothic', sans-serif; background:#f4f6f9; margin:0; padding:20px; }}
  .wrap {{ max-width:640px; margin:auto; background:#fff; border-radius:12px;
           box-shadow:0 4px 16px rgba(0,0,0,.1); overflow:hidden; }}
  .header {{ background:linear-gradient(135deg,#667eea,#764ba2); padding:28px 32px; color:#fff; }}
  .header h1 {{ margin:0; font-size:20px; }}
  .header p  {{ margin:6px 0 0; opacity:.85; font-size:13px; }}
  .body {{ padding:28px 32px; }}
  .meta {{ background:#f8f9fc; border-radius:8px; padding:14px 18px;
           font-size:13px; color:#555; margin-bottom:20px; }}
  .meta span {{ font-weight:700; color:#333; }}
  .content-box {{ background:#fff8e1; border-left:4px solid #f59e0b;
                  border-radius:6px; padding:16px 20px; font-size:14px;
                  line-height:1.8; color:#333; white-space:pre-wrap; }}
  .footer {{ background:#f4f6f9; padding:16px 32px; font-size:12px;
             color:#888; text-align:center; }}
</style></head><body>
<div class="wrap">
  <div class="header">
    <h1>💡 개선 요청이 접수되었습니다</h1>
    <p>DRB LOGIBOT-AI · 개선 요청 알림</p>
  </div>
  <div class="body">
    <div class="meta">
      <p>📅 접수 일시 : <span>{ts}</span></p>
      <p>👥 요청 모드 : <span>{team}</span></p>
    </div>
    <p style="font-size:14px;font-weight:700;color:#444;margin-bottom:10px;">📝 요청 내용</p>
    <div class="content-box">{content}</div>
  </div>
  <div class="footer">본 메일은 DRB LOGIBOT-AI 개선 요청 시스템에서 자동 발송되었습니다.</div>
</div>
</body></html>"""
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[LOGIBOT] 개선 요청 접수 - {datetime.now().strftime('%Y-%m-%d %H:%M')} ({team})"
            msg['From']    = formataddr(("DRB LOGIBOT-AI", self.email_from))
            msg['To']      = ', '.join(self.email_to)
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            logger.info(f"✅ 개선 요청 이메일 전송 완료 ({team})")
            return True
        except Exception as e:
            logger.error(f"❌ 개선 요청 이메일 전송 실패: {e}")
            return False

    def _create_html_email(self, feedback_data: Dict) -> str:
        """HTML 형식의 이메일 본문 생성 (구조화 버전)"""
        query     = feedback_data.get('query', 'N/A')
        answer    = feedback_data.get('answer', 'N/A')
        timestamp = feedback_data.get('timestamp', 'N/A')
        reason    = feedback_data.get('reason', '사유 미입력')

        # 타임스탬프 포맷팅
        try:
            from datetime import datetime as _dt
            ts_display = _dt.fromisoformat(timestamp).strftime("%Y년 %m월 %d일 %H:%M")
        except Exception:
            ts_display = timestamp

        # 답변 마크다운 → HTML 변환 (굵게, 리스트, 표, 줄바꿈)
        def md_to_html(text: str) -> str:
            import re as _re
            # 표(table) 변환
            lines = text.split('\n')
            result, in_table, table_buf = [], False, []
            for line in lines:
                if '|' in line and line.strip().startswith('|'):
                    in_table = True
                    table_buf.append(line)
                else:
                    if in_table:
                        result.append(_render_md_table(table_buf))
                        table_buf = []; in_table = False
                    result.append(line)
            if in_table:
                result.append(_render_md_table(table_buf))
            text = '\n'.join(result)
            # **볼드**
            text = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            # ## 제목
            text = _re.sub(r'^#{1,3}\s+(.+)$', r'<h4 style="margin:10px 0 4px;color:#1e40af;">\1</h4>', text, flags=_re.MULTILINE)
            # - 리스트
            text = _re.sub(r'^[\-\*]\s+(.+)$', r'<li>\1</li>', text, flags=_re.MULTILINE)
            text = _re.sub(r'(<li>.*?</li>(\s*<li>.*?</li>)*)', r'<ul style="margin:6px 0;padding-left:20px;">\1</ul>', text, flags=_re.DOTALL)
            # 줄바꿈
            text = text.replace('\n', '<br>')
            return text

        def _render_md_table(lines):
            import re as _re
            rows = [l for l in lines if not _re.match(r'^\s*\|[\s\-:]+\|\s*$', l)]
            html = '<table style="border-collapse:collapse;width:100%;margin:10px 0;font-size:13px;">'
            for i, row in enumerate(rows):
                cells = [c.strip() for c in row.strip().strip('|').split('|')]
                tag = 'th' if i == 0 else 'td'
                style = ('background:#1e40af;color:white;padding:8px 10px;text-align:left;'
                         if i == 0 else
                         f'padding:7px 10px;border-bottom:1px solid #e2e8f0;background:{"#f8fafc" if i%2==0 else "white"};')
                html += '<tr>' + ''.join(f'<{tag} style="{style}">{c}</{tag}>' for c in cells) + '</tr>'
            html += '</table>'
            return html

        answer_html = md_to_html(answer[:3000] + ("..." if len(answer) > 3000 else ""))
        reason_display = reason if reason.strip() else "사유 미입력"

        html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;background:#f1f5f9;margin:0;padding:20px;}}
  .wrap{{max-width:680px;margin:0 auto;}}
  .header{{background:linear-gradient(135deg,#dc2626,#9f1239);color:white;padding:28px 32px;border-radius:12px 12px 0 0;}}
  .header h1{{margin:0 0 6px;font-size:22px;}}
  .header p{{margin:0;font-size:13px;opacity:.85;}}
  .body{{background:white;padding:28px 32px;border-radius:0 0 12px 12px;border:1px solid #e2e8f0;border-top:none;}}
  .section{{margin-bottom:22px;}}
  .section-title{{font-size:13px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;}}
  .card{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;font-size:14px;color:#334155;line-height:1.7;}}
  .card.red{{border-left:4px solid #dc2626;}}
  .card.blue{{border-left:4px solid #3b82f6;}}
  .card.amber{{border-left:4px solid #f59e0b;}}
  .reason-tag{{display:inline-block;background:#fee2e2;color:#b91c1c;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;margin:2px;}}
  .loop-section{{background:linear-gradient(135deg,#eff6ff,#f0fdf4);border:1px solid #bfdbfe;border-radius:12px;padding:20px 24px;margin-bottom:22px;text-align:center;}}
  .loop-section p{{margin:0 0 14px;font-size:13px;color:#475569;line-height:1.7;}}
  .loop-btn{{display:inline-block;background:linear-gradient(135deg,#0ea5e9,#6366f1);color:#ffffff !important;text-decoration:none !important;padding:12px 28px;border-radius:8px;font-size:14px;font-weight:700;letter-spacing:.3px;box-shadow:0 4px 12px rgba(99,102,241,.35);}}
  .loop-btn:hover{{opacity:.9;}}
  .loop-hint{{margin:10px 0 0;font-size:11px;color:#94a3b8;}}
  .meta{{font-size:12px;color:#94a3b8;margin-top:20px;text-align:right;border-top:1px solid #f1f5f9;padding-top:12px;}}
  .footer{{text-align:center;margin-top:18px;font-size:11px;color:#94a3b8;}}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>👎 부정 피드백 알림</h1>
    <p>DRB 물류 AI 챗봇 · 답변 품질 개선이 필요합니다</p>
  </div>
  <div class="body">

    <div class="section">
      <div class="section-title">📝 사용자 질문</div>
      <div class="card red">{query}</div>
    </div>

    <div class="section">
      <div class="section-title">🤖 AI 답변</div>
      <div class="card blue">{answer_html}</div>
    </div>

    <div class="section">
      <div class="section-title">⚠️ 부정 피드백 사유</div>
      <div class="card amber">
        {''.join(f'<span class="reason-tag">{r.strip()}</span>' for r in reason_display.replace('| 추가의견:', '|').split('/'))}
        {'<br><span style="font-size:13px;color:#78350f;margin-top:8px;display:block;">💬 추가 의견: ' + reason_display.split('추가의견:')[1].strip() + '</span>' if '추가의견:' in reason_display else ''}
      </div>
    </div>

    <div class="loop-section">
      <p>
        📋 <strong>팀원 여러분의 소중한 의견이 AI 학습 데이터 개선에 직접 반영됩니다.</strong><br>
        아래 버튼을 클릭하여 학습 데이터 문서에 개선 내용을 직접 기록해 주세요.<br>
        작성해 주신 피드백은 더 정확한 AI 답변을 만드는 데 큰 힘이 됩니다. 🙏
      </p>
      <a href="https://drbworld-my.sharepoint.com/:x:/p/shin_tae_hwan/IQAg1gyD-21uSKlKo0KBbSq7ATansZ4KE7m3nctSSvyd7I4?e=ooGJuI"
         class="loop-btn" target="_blank">
        📝 &nbsp;학습 데이터 개선 문서 열기
      </a>
      <div class="loop-hint">※ 사내 Microsoft 365 계정으로 로그인이 필요할 수 있습니다</div>
    </div>

    <div class="meta">⏰ 피드백 시각: {ts_display}</div>
  </div>
  <div class="footer">
    이 메일은 부정 피드백 발생 시 자동으로 발송됩니다 · DRB LOGIBOT-AI
  </div>
</div>
</body>
</html>"""
        return html

class OnPremiseGemmaLLM(LLM):
    """온프레미스 Gemma LLM"""
    api_url: str = ONPREMISE_API_URL
    model: str = ONPREMISE_MODEL
    timeout: int = ONPREMISE_TIMEOUT
    max_retries: int = 3
    temperature: float = 0.2
    _last_call_ts: float = PrivateAttr(default=0.0)
    _rate_limit_delay: float = PrivateAttr(default=1.0)
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"api_url": self.api_url, "model": self.model}
    
    @property
    def _llm_type(self) -> str:
        return "onpremise_gemma"
    
    def _enforce_rate_limit(self):
        current_time = time.time()
        time_since_last_call = current_time - self._last_call_ts
        
        if time_since_last_call < self._rate_limit_delay:
            sleep_time = self._rate_limit_delay - time_since_last_call
            time.sleep(sleep_time)
        
        self._last_call_ts = time.time()
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        self._enforce_rate_limit()
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "stream": False,
            "max_tokens": 2048
        }
        
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    self.api_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if "message" in data and "content" in data["message"]:
                        return data["message"]["content"]
                    elif "content" in data:
                        return data["content"]
                    elif "choices" in data and len(data["choices"]) > 0:
                        return data["choices"][0].get("message", {}).get("content", "")
                    else:
                        raise ValueError(f"Unexpected response format: {data}")
                
                elif response.status_code == 429:
                    if attempt < self.max_retries:
                        time.sleep(5 * attempt)
                    else:
                        raise RuntimeError("Rate limit exceeded")
                else:
                    if attempt < self.max_retries:
                        time.sleep(2 * attempt)
                    else:
                        raise RuntimeError(f"API failed: {response.text}")
            
            except requests.Timeout:
                if attempt < self.max_retries:
                    time.sleep(2 * attempt)
                else:
                    raise RuntimeError(f"API timeout after {self.max_retries} retries")
            
            except Exception as e:
                logger.error(f"API 호출 오류 (시도 {attempt}): {e}")
                if attempt < self.max_retries:
                    time.sleep(2 * attempt)
                else:
                    raise


class RAGChainWrapper:
    """RAG 체인 래퍼 (검색 최적화)"""
    def __init__(self, vectorstore, llm, embeddings, qdrant_client):
        self.vectorstore = vectorstore
        self.llm = llm
        self.embeddings = embeddings
        self.qdrant_client = qdrant_client
        self.prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)    
    
    @lru_cache(maxsize=100)
    def extract_material_code(self, query: str) -> Optional[str]:
        """자재코드 추출"""
        patterns = [
            r'\b(\d{7})\b',
            r'자재코드[:\s]*(\d{7})',
            r'코드[:\s]*(\d{7})',
            r'품번[:\s]*(\d{7})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                return match.group(1)
        return None
    
    def keyword_search_optimized(self, material_code: str, limit: int = 5):
        """최적화된 키워드 검색 (필터 사용)"""
        try:
            search_result = self.qdrant_client.scroll(
                collection_name=QDRANT_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="material_code",
                            match=MatchValue(value=material_code)
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
                with_vectors=False
            )
            
            points, _ = search_result
            
            matched_docs = []
            for point in points:
                payload = point.payload
                matched_docs.append({
                    'id': point.id,
                    'content': payload.get('page_content', ''),
                    'metadata': payload.get('metadata', {}),
                    'score': 1.0
                })
            
            logger.info(f"키워드 검색 (필터): {len(matched_docs)}개")
            return matched_docs
            
        except Exception as e:
            logger.error(f"키워드 검색 실패: {e}")
            return []
        
    def _detect_domain(self, query: str, keyword_doc_content: str = "") -> str:
        """
        질문 + 검색된 문서 내용을 기반으로 도메인 판별
        반환값: 'conveyor' | 'crawler' | 'export' | 'general'
        """
        combined = query + " " + keyword_doc_content

        # 컨베어벨트 도메인
        conveyor_kw = ["컨베어", "컨베이어", "직경", "롤", "NN", "EP", "포규격", "심체", "컨베어벨트"]
        if any(k in combined for k in conveyor_kw):
            return "conveyor"

        # 크롤러/러버트랙 도메인
        crawler_kw = ["크롤러", "러버트랙", "RT", "트랙", "배차", "몇 톤", "파렛트", "Rubber Track"]
        if any(k in combined for k in crawler_kw):
            return "crawler"

        # 수출 포장 도메인
        export_kw = ["박스", "포장량", "컨테이너", "B01", "B02", "N18", "N19", "마대", "우든"]
        if any(k in combined for k in export_kw):
            return "export"

        return "general"

    def fetch_whole_docs(self, sheet_names: list, limit: int = 5):
        """WHOLE/QA 전략으로 저장된 특정 시트 문서를 페이로드 필터로 가져옴"""
        from langchain_core.documents import Document
        docs = []
        try:
            for sheet in sheet_names:
                result = self.qdrant_client.scroll(
                    collection_name=QDRANT_COLLECTION,
                    scroll_filter=Filter(
                        must=[FieldCondition(
                            key="metadata.sheet_name",
                            match=MatchValue(value=sheet)
                        )]
                    ),
                    limit=limit,
                    with_payload=True,
                    with_vectors=False
                )
                for point in result[0]:
                    payload = point.payload
                    doc = Document(
                        page_content=payload.get('page_content', ''),
                        metadata=payload.get('metadata', {})
                    )
                    if doc.page_content:
                        docs.append((doc, 0.9))
        except Exception as e:
            logger.warning(f"WHOLE 문서 보완 실패: {e}")
        return docs

    # 도메인별 보완 시트 매핑
    DOMAIN_SUPPLEMENT_SHEETS = {
        "conveyor": ["컨베어벨트 직경 산출 수식"],
        "crawler" : ["차량 데이터"],
        "export"  : ["수출 포장량 산출 수식", "포장량 산출 데이터"],
        "general" : ["차량 데이터"],
    }

    def hybrid_search(self, query: str, k: int = 50):
        material_code = self.extract_material_code(query)
        results = []

        if material_code:
            keyword_results = self.keyword_search_optimized(material_code, limit=5)

            if keyword_results:
                from langchain_core.documents import Document
                for result in keyword_results:
                    doc = Document(
                        page_content=result['content'],
                        metadata=result['metadata']
                    )
                    results.append((doc, result['score']))

                # 도메인 판별 후 필요한 수식/규칙 문서 보완
                first_doc_content = keyword_results[0].get('content', '')
                domain = self._detect_domain(query, first_doc_content)
                supplement_sheets = self.DOMAIN_SUPPLEMENT_SHEETS.get(domain, ["차량 데이터"])

                whole_docs = self.fetch_whole_docs(supplement_sheets, limit=1)
                results.extend(whole_docs)
                logger.info(f"자재코드 검색: {len(keyword_results)}개 | 도메인: {domain} | 보완: {supplement_sheets} ({len(whole_docs)}개)")
                return results

        try:
            vector_results = self.vectorstore.similarity_search_with_score(query, k=50)

            if len(vector_results) > 3:
                filtered_results = [(doc, score) for doc, score in vector_results if score >= 0.15]
            else:
                filtered_results = vector_results

            logger.info(f"벡터 검색 결과 확보: {len(filtered_results)}개")
            return filtered_results
        except Exception as e:
            logger.error(f"벡터 검색 실패: {e}")
            return []
          
class LoggingSystem:
    """질문/답변 로깅 시스템"""
    def __init__(self, qdrant_client: QdrantClient, embeddings: OllamaEmbeddings):
        self.client = qdrant_client
        self.embeddings = embeddings
        self._ensure_log_collections()
    
    def _ensure_log_collections(self):
        """로깅 전용 컬렉션 생성"""
        try:
            collections = self.client.get_collections().collections
            existing_names = [c.name for c in collections]
            
            sample_vector = self.embeddings.embed_query("test")
            vector_size = len(sample_vector)
            
            if QUERY_LOG_COLLECTION not in existing_names:
                self.client.create_collection(
                    collection_name=QUERY_LOG_COLLECTION,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                )
                logger.info(f"✅ {QUERY_LOG_COLLECTION} 생성 (로깅 전용)")
            
            if ANSWER_LOG_COLLECTION not in existing_names:
                self.client.create_collection(
                    collection_name=ANSWER_LOG_COLLECTION,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                )
                logger.info(f"✅ {ANSWER_LOG_COLLECTION} 생성 (로깅 전용)")
                
        except Exception as e:
            logger.error(f"로그 컬렉션 오류: {e}")
    
    def log_query(self, query: str, metadata: Dict = None):
        """질문 로깅"""
        try:
            query_vector = self.embeddings.embed_query(query)
            query_id = hashlib.md5(
                f"{query}_{datetime.now().isoformat()}".encode()
            ).hexdigest()
            
            payload = {
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "metadata": json.dumps(metadata or {}, ensure_ascii=False)
            }
            
            self.client.upsert(
                collection_name=QUERY_LOG_COLLECTION,
                points=[PointStruct(id=query_id, vector=query_vector, payload=payload)]
            )
            
            return query_id
            
        except Exception as e:
            logger.error(f"질문 로깅 실패: {e}")
            return None
    
    def log_answer(self, query_id: str, query: str, answer: str, sources: List[Dict], metadata: Dict = None):
        """답변 로깅"""
        try:
            answer_vector = self.embeddings.embed_query(answer)
            answer_id = hashlib.md5(
                f"{answer}_{datetime.now().isoformat()}".encode()
            ).hexdigest()
            
            payload = {
                "query_id": query_id,
                "query": query,
                "answer": answer,
                "sources": json.dumps(sources, ensure_ascii=False),
                "timestamp": datetime.now().isoformat(),
                "answer_length": len(answer),
                "source_count": len(sources),
                "metadata": json.dumps(metadata or {}, ensure_ascii=False)
            }
            
            self.client.upsert(
                collection_name=ANSWER_LOG_COLLECTION,
                points=[PointStruct(id=answer_id, vector=answer_vector, payload=payload)]
            )
            
        except Exception as e:
            logger.error(f"답변 로깅 실패: {e}")


class LearningSystem:
    """학습 시스템 + 이메일 알림"""
    def __init__(self, qdrant_client: QdrantClient, embeddings: OllamaEmbeddings, 
                 email_notifier: Optional[EmailNotifier] = None):
        self.client = qdrant_client
        self.embeddings = embeddings
        self.good_collection = LEARNING_COLLECTION
        self.bad_collection = BAD_FEEDBACK_COLLECTION
        self.email_notifier = email_notifier
        self._ensure_collections()
    
    def _ensure_collections(self):
        """학습용 컬렉션 생성"""
        try:
            collections = self.client.get_collections().collections
            existing_names = [c.name for c in collections]
            
            sample_vector = self.embeddings.embed_query("test")
            vector_size = len(sample_vector)
            
            if self.good_collection not in existing_names:
                self.client.create_collection(
                    collection_name=self.good_collection,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                )
                logger.info(f"✅ {self.good_collection} 생성 (학습용)")
            
            if self.bad_collection not in existing_names:
                self.client.create_collection(
                    collection_name=self.bad_collection,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                )
                logger.info(f"✅ {self.bad_collection} 생성 (학습용)")
                
        except Exception as e:
            logger.error(f"컬렉션 오류: {e}")
    
    def save_interaction(self, query: str, answer: str, sources: List[Dict], 
                        feedback_score: Optional[float] = None):
        """긍정 피드백 상호작용 저장"""
        try:
            query_vector = self.embeddings.embed_query(query)
            
            interaction_id = hashlib.md5(
                f"{query}_{datetime.now().isoformat()}".encode()
            ).hexdigest()
            
            metadata = {
                "query": query,
                "answer": answer,
                "sources": json.dumps(sources, ensure_ascii=False),
                "timestamp": datetime.now().isoformat(),
                "feedback_score": feedback_score or 0.0,
                "usage_count": 1,
                "avg_quality": sum(s.get('score', 0) for s in sources) / len(sources) if sources else 0.0
            }
            
            self.client.upsert(
                collection_name=self.good_collection,
                points=[PointStruct(id=interaction_id, vector=query_vector, payload=metadata)]
            )
            
        except Exception as e:
            logger.error(f"상호작용 저장 실패: {e}")
    
    def save_bad_feedback(self, query: str, answer: str, sources: List[Dict],
                          reason: str = ""):
        """
        부정 피드백 저장 + 이메일 알림 발송 (사유 포함)
        """
        try:
            query_vector = self.embeddings.embed_query(query)
            feedback_id = hashlib.md5(
                f"{query}_{datetime.now().isoformat()}_bad".encode()
            ).hexdigest()
            timestamp = datetime.now().isoformat()

            metadata = {
                "query": query,
                "answer": answer,
                "sources": json.dumps(sources, ensure_ascii=False),
                "timestamp": timestamp,
                "feedback_type": "bad",
                "reason": reason,
            }

            self.client.upsert(
                collection_name=self.bad_collection,
                points=[PointStruct(id=feedback_id, vector=query_vector, payload=metadata)]
            )
            logger.info(f"💾 부정 피드백 저장: {query[:30]}... | 사유: {reason[:30]}")

            if self.email_notifier and self.email_notifier.enabled:
                feedback_data = {
                    "query": query,
                    "answer": answer,
                    "sources": sources,
                    "timestamp": timestamp,
                    "reason": reason,
                }
                email_thread = threading.Thread(
                    target=self.email_notifier.send_bad_feedback_notification,
                    args=(feedback_data,),
                    daemon=True
                )
                email_thread.start()

        except Exception as e:
            logger.error(f"Bad 피드백 실패: {e}")
    
    def search_similar_interactions(self, query: str, limit: int = 3, 
                                   min_score: float = 0.7) -> List[Dict]:
        """과거 유사 상호작용 검색"""
        try:
            query_vector = self.embeddings.embed_query(query)
            
            results = self.client.search(
                collection_name=self.good_collection,
                query_vector=query_vector,
                limit=limit,
                score_threshold=min_score
            )
            
            interactions = []
            for result in results:
                interactions.append({
                    'query': result.payload.get('query'),
                    'answer': result.payload.get('answer'),
                    'score': result.score,
                    'usage_count': result.payload.get('usage_count', 1)
                })
                
                # 사용 횟수 업데이트
                self.client.set_payload(
                    collection_name=self.good_collection,
                    payload={'usage_count': result.payload.get('usage_count', 1) + 1},
                    points=[result.id]
                )
            
            return interactions
            
        except Exception as e:
            logger.error(f"과거 데이터 검색 실패: {e}")
            return []
    
    def update_feedback(self, query: str, feedback_score: float, answer: str = "",
                        sources: List[Dict] = [], reason: str = ""):
        """피드백 업데이트"""
        try:
            if feedback_score >= 0.5:
                query_vector = self.embeddings.embed_query(query)
                results = self.client.search(
                    collection_name=self.good_collection,
                    query_vector=query_vector,
                    limit=1
                )
                if results:
                    point_id = results[0].id
                    current_score = results[0].payload.get('feedback_score', 0.0)
                    new_score = (current_score + feedback_score) / 2
                    self.client.set_payload(
                        collection_name=self.good_collection,
                        payload={'feedback_score': new_score},
                        points=[point_id]
                    )
            else:
                # 부정 피드백 시 사유 포함 저장 + 이메일
                self.save_bad_feedback(query, answer, sources, reason=reason)
        except Exception as e:
            logger.error(f"피드백 업데이트 실패: {e}")


def clean_cache():
    """캐시 정리"""
    global response_cache
    current_time = datetime.now()
    
    with cache_lock:
        expired_keys = [
            k for k, v in response_cache.items() 
            if (current_time - v['timestamp']).seconds > CACHE_TTL
        ]
        
        for key in expired_keys:
            del response_cache[key]


def setup_rag_chain():
    """RAG 체인 설정"""
    logger.info("RAG 체인 초기화...")
    
    llm = OnPremiseGemmaLLM()
    embeddings = OllamaEmbeddings(model=OLLAMA_EMBEDDING_MODEL, base_url=OLLAMA_HOST)
    qdrant_client = QdrantClient(url=QDRANT_HOST)
    vectorstore = Qdrant(client=qdrant_client, collection_name=QDRANT_COLLECTION, embeddings=embeddings)
    
    rag_chain = RAGChainWrapper(vectorstore, llm, embeddings, qdrant_client)
    logger.info("✅ RAG 체인 완료")
    return rag_chain


def search_ddg(query: str) -> str:
    """웹 검색"""
    try:
        results = DDGS().text(query, max_results=5, region='kr-kr')
        
        if not results:
            return ""
        
        context = []
        for i, r in enumerate(results, 1):
            context.append(f"[출처 {i}] {r['title']}\n{r['body']}")
        
        return "\n\n".join(context)
        
    except Exception as e:
        logger.error(f"웹 검색 오류: {e}")
        return ""


def format_answer(answer: str) -> str:
    """LaTeX 변환 및 숫자 점수 제거"""
    if not answer:
        return ""

    # 유사도 점수 패턴 제거
    answer = re.sub(r'\s?\d\.\d{3}\b', '', answer)
    
    # LaTeX 변환
    answer = re.sub(r'\\frac\{(.+?)\}\{(.+?)\}', r'(\1 / \2)', answer)
    answer = answer.replace(r'\times', '×').replace(r'\cdot', '·')
    answer = answer.replace(r'\left\lfloor', '[').replace(r'\right\rfloor', ']')
    answer = answer.replace(r'\left(', '(').replace(r'\right)', ')')
    answer = answer.replace('[ ', '').replace(' ]', '')
    answer = answer.replace(r'\,', ' ')
    
    return answer.strip()


def build_conversation_context(context_history: List[Dict]) -> str:
    """
    대화 맥락 구성.
    - 최근 5턴까지 참조 (기존 3턴)
    - 답변은 최대 300자 (기존 150자) → 맥락 정확도 향상
    - 자재코드·수치 등 핵심 키워드가 있으면 전체 보존
    """
    if not context_history:
        return ""

    # 최근 5턴 사용
    recent = context_history[-5:]
    context_str = "=== 이번 대화 히스토리 (최신순) ===\n"

    for idx, ctx in enumerate(reversed(recent), 1):
        q = ctx.get('query', '')
        a = ctx.get('answer', '')

        # 자재코드(7자리 숫자) 또는 수치 계산 포함 시 답변 전체 보존
        import re as _re
        has_code    = bool(_re.search(r'\b\d{7}\b', q + a))
        has_calc    = any(kw in q for kw in ['계산', '직경', '배차', '파렛트', '톤', '박스', '포장'])
        answer_limit = len(a) if (has_code or has_calc) else 300

        context_str += f"\n[{idx}번째 이전 대화]\n"
        context_str += f"사용자: {q}\n"
        context_str += f"AI 답변: {a[:answer_limit]}{'...(이하 생략)' if len(a) > answer_limit else ''}\n"

    context_str += "\n위 대화 히스토리를 반드시 참고하여 일관성 있게 답변하세요.\n"
    return context_str


def process_query(query: str, rag_chain: RAGChainWrapper, learning_system: LearningSystem, 
                 logging_system: LoggingSystem, context: List[Dict] = None) -> Tuple[str, List[Dict], bool]:
    """쿼리 처리"""
    
    # 로깅만 수행
    query_id = logging_system.log_query(query, metadata={"context_length": len(context or [])})

    # 캐시 키: 질문 + 직전 대화 턴의 쿼리를 포함 → 맥락이 다르면 다른 답변
    prev_queries = "||".join(c.get("query", "") for c in (context or [])[-3:])
    cache_key = hashlib.md5(f"{query}|{prev_queries}".encode()).hexdigest()
    
    # 캐시 확인
    with cache_lock:
        if cache_key in response_cache:
            cached_data = response_cache[cache_key]
            if (datetime.now() - cached_data['timestamp']).seconds < CACHE_TTL:
                logger.info("✅ 캐시 응답")
                return cached_data['answer'], cached_data['sources'], cached_data.get('has_table', False)
    
    # learning_history에서 유사 상호작용 검색
    similar_interactions = learning_system.search_similar_interactions(query, limit=2, min_score=0.85)
    
    history_context = ""
    if similar_interactions:
        history_context = "참고: 과거 유사 질문 (learning_history)\n"
        for idx, interaction in enumerate(similar_interactions, 1):
            history_context += f"\n[{idx}] {interaction['query']}\n{interaction['answer'][:200]}...\n"
    
    # 대화 맥락 구성
    conversation_context = build_conversation_context(context or [])
    
    answer = ""
    sources = []
    use_web_search = False
    has_table = False
    
    table_keywords = ["표로", "표 형식", "테이블", "표를", "표 만들"]
    is_table_request = any(kw in query for kw in table_keywords)
    search_k = 7
    list_keywords = ["몇 개", "전부", "목록", "리스트", "어디"]
    if any(kw in query for kw in list_keywords):
        search_k = 15 # 목록 질문 시 더 넓게 검색
    
    try:
        # logistics_data에서 검색
        filtered_docs = rag_chain.hybrid_search(query, k=search_k)

        # 문서가 1개라도 있으면 RAG 시도 (기존 < 2 조건이 웹서치 강제 유발)
        if not filtered_docs:
            use_web_search = True
        else:
            # [문서 N] 태그 없이 순수 내용만 연결
            context_text = "\n\n---\n\n".join([
                doc.page_content
                for doc, _ in filtered_docs
            ])

            sources = [{
                'name': (
                    doc.metadata.get('file_name')
                    or os.path.basename(doc.metadata.get('source', ''))
                    or doc.metadata.get('sheet_name', '검색 결과')
                ),
                'page_content': doc.page_content,
                'sheet_name': doc.metadata.get('sheet_name', ''),
                'internal_score': float(score),
                'page': doc.metadata.get('page', 'N/A')
            } for doc, score in filtered_docs]

            if len(context_text) > 4000:
                context_text = context_text[:4000] + "\n..."

            if is_table_request:
                has_table = True

            # 프롬프트 생성 (템플릿 변수와 일치)
            formatted_prompt = rag_chain.prompt_template.format(
                context=context_text,
                input=query,
                history_context=history_context if history_context else "없음",
                conversation_context=conversation_context if conversation_context else "없음"
            )

            answer = rag_chain.llm._call(formatted_prompt)

            if "|" in answer and "---" in answer:
                has_table = True

            # 웹서치 fallback 조건 강화: 명백히 빈 답변일 때만
            # "정보가 없습니다" 등 포함해도 RAG 답변으로 반환 (웹서치보다 내부 데이터 우선)
            if not answer or len(answer.strip()) < 20:
                use_web_search = True
            
    except Exception as e:
        logger.error(f"검색 실패: {e}")
        use_web_search = True
    
    # 웹 검색
    if use_web_search:
        web_context = search_ddg(query)
        sources = [{'name': 'Web Search', 'score': 0.5, 'page': 'N/A'}]
        
        if web_context:
            enhanced_prompt = f"""웹 검색 결과:

{web_context}

{conversation_context}

{history_context}

질문: {query}

{"⚠️ 표 형식으로 작성하세요." if is_table_request else ""}

답변:
"""
            try:
                answer = rag_chain.llm._call(enhanced_prompt)
                answer += "\n\n🌐 웹 검색 기반"
                
                if "|" in answer and "---" in answer:
                    has_table = True
                    
            except Exception as e:
                answer = "답변 생성 실패"
        else:
            answer = "정보를 찾을 수 없습니다."
    
    # learning_history에 저장
    learning_system.save_interaction(query, answer, sources)
    
    # 답변 포맷팅
    answer = format_answer(answer)
    
    # 로깅만 수행
    logging_system.log_answer(
        query_id=query_id,
        query=query,
        answer=answer,
        sources=sources,
        metadata={"has_table": has_table, "use_web_search": use_web_search}
    )
    
    # 캐시 저장
    with cache_lock:
        response_cache[cache_key] = {
            'answer': answer,
            'sources': sources,
            'has_table': has_table,
            'timestamp': datetime.now()
        }
    
    if len(response_cache) > 100:
        clean_cache()
    
    return answer, sources, has_table


# 초기화
try:
    RAG_CHAIN = setup_rag_chain()
    EMAIL_NOTIFIER = EmailNotifier()
    LEARNING_SYSTEM = LearningSystem(RAG_CHAIN.qdrant_client, RAG_CHAIN.embeddings, EMAIL_NOTIFIER)
    LOGGING_SYSTEM = LoggingSystem(RAG_CHAIN.qdrant_client, RAG_CHAIN.embeddings)
    logger.info("✅ 시스템 완료")
    logger.info("=" * 60)
    logger.info("📊 컬렉션 용도:")
    logger.info("  - logistics_data: 메인 문서 (답변 생성 시 사용)")
    logger.info("  - learning_history: 긍정 피드백 데이터 (답변 생성 시 사용)")
    logger.info("  - bad_feedback_history: 부정 피드백 데이터 (참고용 + 이메일 알림)")
    logger.info("  - query_logs: 질문 로그 (로깅 전용)")
    logger.info("  - answer_logs: 답변 로그 (로깅 전용)")
    logger.info("=" * 60)
    if EMAIL_NOTIFIER.enabled:
        logger.info(f"📧 이메일 알림: 활성화 → {', '.join(EMAIL_NOTIFIER.email_to)}")
    else:
        logger.info("📧 이메일 알림: 비활성화")
    logger.info("=" * 60)
except Exception as e:
    logger.exception("❌ 초기화 실패")
    RAG_CHAIN = None
    LEARNING_SYSTEM = None
    LOGGING_SYSTEM = None
    EMAIL_NOTIFIER = None


def get_rag_response(query: str, context: List[Dict] = None) -> Dict[str, Any]:
    """RAG 응답 생성"""
    global RAG_CHAIN, LEARNING_SYSTEM, LOGGING_SYSTEM
    
    answer, sources, has_table = process_query(query, RAG_CHAIN, LEARNING_SYSTEM, LOGGING_SYSTEM, context)
    
    # 답변에서 유사도 점수 제거
    clean_answer = re.sub(r'\s?\d\.\d{3}\b', '', answer).strip()

    # 출처 정보 구성 (중복 제거)
    unique_sources_data = []
    seen = set()
    for s in (sources or []):
        if isinstance(s, dict):
            meta = s.get('metadata', {})
            text = s.get('page_content', s.get('content', ''))
        else:
            meta = getattr(s, 'metadata', {})
            text = getattr(s, 'page_content', '')

        f_name = meta.get('file_name', meta.get('name', '참고 문서'))
        f_name = re.sub(r'\s?\d\.\d{3}\b', '', str(f_name)).strip()

        if f_name and text and f_name not in seen:
            unique_sources_data.append({"name": f_name, "content": text})
            seen.add(f_name)

    return {
        "answer": clean_answer,
        "sources": unique_sources_data[:3],
        "has_table": has_table,
        "cached": False
    }


def submit_feedback(query: str, feedback_score: float, answer: str = "",
                    sources: List[Dict] = [], reason: str = ""):
    """
    피드백 제출 (부정 피드백 시 사유 포함 자동 이메일 발송)
    """
    global LEARNING_SYSTEM
    if LEARNING_SYSTEM:
        LEARNING_SYSTEM.update_feedback(query, feedback_score, answer, sources, reason=reason)
    else:
        logger.error("❌ LEARNING_SYSTEM 미초기화")
        
def analyze_logistics_data(df: pd.DataFrame) -> str:
    try:
        # 중량 관련 컬럼 탐색 (대소문자 무시)
        weight_col = [c for c in df.columns if '중량' in str(c) or 'weight' in str(c).lower()]
        if not weight_col:
            return "❌ 엑셀 파일 내에 '중량' 관련 컬럼을 찾을 수 없습니다."
        
        total_weight = df[weight_col[0]].sum()
        
        # 배차 로직 (단순화)
        if total_weight <= 1000: truck = "1톤 트럭"
        elif total_weight <= 5000: truck = "5톤 카고"
        elif total_weight <= 11000: truck = "11톤 윙바디"
        else: truck = "25톤 트레일러"
            
        return f"📊 **분석 결과**: 합계 중량 {total_weight:,.1f}kg, 추천 차량은 **{truck}** 입니다."
    except Exception as e:
        return f"❌ 엑셀 분석 중 오류: {str(e)}"

def analyze_pdf_logistics(file_bytes):
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        
        # 중량 숫자 추출 (정규표현식: 중량 뒤의 숫자와 단위 매칭)
        weights = re.findall(r'(?:중량|Weight)\s*[:：]?\s*([\d,.]+)', full_text)
        if weights:
            total_w = sum([float(w.replace(',', '')) for w in weights])
            return f"📄 **PDF 분석 완료**: 감지된 총 중량은 **{total_w:,.1f}kg**입니다. 배차 분석을 진행할까요?"
        
        return "📄 PDF 텍스트는 추출했으나, '중량' 키워드와 수치를 찾지 못했습니다."
    except Exception as e:
        return f"❌ PDF 처리 실패: {str(e)}"
    
def get_db_transport_advice(total_pallets: float, total_weight_kg: float = 0.0):
    """
    차량 데이터 WHOLE 문서(파이프 구분 텍스트)를 파싱해 최적 차량 추천
    total_pallets   : 필요 파렛트 수 (부피 기준)
    total_weight_kg : 총 중량 kg (0이면 중량 조건 무시)
    반환 dict 추가 키: max_weight_ton, weight_ok
    """
    PLT_W, PLT_L = 1.1, 1.1  # 표준 파렛트 1100×1100mm

    try:
        client = QdrantClient(url=QDRANT_HOST)

        search_result = client.scroll(
            collection_name="logistics_data",
            scroll_filter=models.Filter(
                must=[models.FieldCondition(
                    key="metadata.sheet_name",
                    match=models.MatchValue(value="차량 데이터")
                )]
            ),
            limit=10
        )[0]

        if not search_result:
            return None

        content = search_result[0].payload.get("page_content", "")
        total_weight_ton = total_weight_kg / 1000.0

        candidates = []
        for line in content.split('\n'):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 4:
                continue
            name = parts[0]
            if not name or '톤수' in name or name.startswith('[') or '특이사항' in name or '높이' in name:
                continue
            try:
                length = float(re.search(r'([\d.]+)m', parts[2]).group(1))
                width  = float(re.search(r'([\d.]+)m', parts[3]).group(1))
            except Exception:
                continue

            # 최대중량 파싱 (예: "~ 1.32", "1.33 ~ 2.75")
            max_weight_ton = None
            if len(parts) >= 2:
                nums = re.findall(r'[\d.]+', parts[1])
                if nums:
                    max_weight_ton = float(nums[-1])

            cols    = int(width  / PLT_W)
            rows    = int(length / PLT_L)
            max_plt = cols * rows

            if max_plt < total_pallets:
                continue

            weight_ok = True
            if total_weight_ton > 0 and max_weight_ton is not None:
                weight_ok = total_weight_ton <= max_weight_ton

            candidates.append({
                "name"          : name,
                "spec"          : f"길이 {length}m / 폭 {width}m",
                "max_plt"       : max_plt,
                "max_weight_ton": max_weight_ton,
                "weight_ok"     : weight_ok,
            })

        if not candidates:
            return None

        # 중량·부피 모두 충족 우선, 없으면 부피만 충족으로 fallback
        ok_both = [c for c in candidates if c["weight_ok"]]
        pool    = ok_both if ok_both else candidates
        return sorted(pool, key=lambda x: x['max_plt'])[0]

    except Exception as e:
        logger.error(f"⚠️ DB 배차 조회 중 오류: {e}")
        return None

    except Exception as e:
        logger.error(f"⚠️ DB 배차 조회 중 오류: {e}")
        return None

# 메인 함수
if __name__ == "__main__":
    test_queries = [
        "6004010 자재 정보",
        "컨베어벨트 목록을 표로 보여줘"
    ]
    
    conversation_context = []
    
    for test_q in test_queries:
        try:
            print(f"\n{'='*60}\n질문: {test_q}\n{'='*60}")
            
            start_time = time.time()
            result = get_rag_response(test_q, context=conversation_context)
            elapsed = time.time() - start_time
            
            print(f"\n{result['answer']}")
            print(f"\n표 포함: {result['has_table']}")
            print(f"\n⏱️ 응답 시간: {elapsed:.2f}초\n{'='*60}")
            
            conversation_context.append({
                "query": test_q,
                "answer": result['answer'],
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.exception(f"테스트 실패: {e}")