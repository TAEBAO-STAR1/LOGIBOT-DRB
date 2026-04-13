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

[답변 작성 규칙]
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

12. **지입기사 납품 동선/노선 규칙**: '지입기사', '납품 동선', '노선', '배달 경로', '기사 노선', '동선' 키워드가 포함된 질문은
    반드시 [지입 차량(기사) 노선 데이터]를 참조하여 아래 규칙을 엄격히 따르세요.

    [핵심 해석 규칙 - 반드시 준수]
    - 데이터에 월~금요일 행이 모두 있는 기사 = 주 5일(월~금) 매일 운행하는 기사입니다. "특정 요일만 운행"이라고 절대 말하지 마세요.
    - 요일별 도착지가 다른 것은 "그 날에만 운행"이 아니라 "그 날의 납품 코스(동선)가 다름"을 의미합니다.
    - 데이터에 등록된 기사 전원(부산공장 기사 + 중부물류센터 기사)을 빠짐없이 모두 답변에 포함하세요. 누락하면 오답입니다.

    [답변 형식]
    기사별로 구분하여 요일별 납품 동선을 정리하세요:
    ## 기사명 (소속)
    | 요일 | 납품 동선 |
    특정 요일을 질문한 경우 해당 요일 행만 추출해서 보여주세요.

13. **자재코드 단독 질문 규칙**: 자재코드(7자리 숫자)만 입력하고 자재 종류를 명시하지 않은 질문에도
    [참고 데이터]에 해당 코드 정보가 포함되어 있으면 반드시 아래 순서로 답변하세요.
    ① 자재 종류 자동 식별 (컨베어벨트/주름혹벨트/크롤러 러버트랙 중 어느 시트에서 왔는지)
    ② 자재내역(제품명), 자재그룹, 중량 등 기본 정보 먼저 제시
    ③ 질문에 "중량", "적재", "배차", "직경" 등 추가 키워드가 있으면 해당 계산도 함께 수행
    ④ 시트 구분 없이 코드만으로 모든 정보를 제공할 수 있음을 전제로 답변하세요.

14. **전동 수출 파렛트 CBM 계산 규칙**: 'CBM', '파렛트 부피', '수출 CBM' 관련 질문은
    반드시 아래 확정값을 사용하세요. 임의로 계산하거나 다른 수치를 사용하지 마세요.

    [전동수출 파렛트 CBM 확정값 — 물류팀 운영 규칙]
    - 파렛트 1개 규격: 가로 1.1m × 세로 1.1m × 높이 2.2m = **2.662 CBM**
    - N파렛트 CBM = 2.662 × N
    - 예시: 8파렛트 = 2.662 × 8 = **21.296 CBM**

    [답변 형식]
    | 항목 | 값 |
    |------|-----|
    | 파렛트 규격 | 1,100 × 1,100 × 2,200 mm |
    | 파렛트 1개 CBM | 2.662 CBM |
    | 파렛트 수량 | N PLT |
    | 총 CBM | 2.662 × N = OO.OOO CBM |

15. **국내 출고 운송 방식 판단 규칙**: '직송', '화물', '택배', '출고' 키워드 포함 시
    자재코드로 1PC당 중량 확인 → 총 중량 계산 → 도착지 구간 기준 적용.
    웹 검색 절대 사용 금지.
    - 부산시내: 150kg 이하 화물/택배, 초과 직송
    - 녹산·대저·명지·경남권: 300kg 이하 화물/택배, 초과 직송
    - 서울·광주·대구 등 장거리: 800kg 이하 화물/택배, 초과 직송

16. **박스 적재량 및 파렛트 사이즈 규칙**: '몇 박스', '1파렛트당', 'PLT당 적재' 관련 질문은
    [물류팀 운영 규칙]을 1순위로 참조. [파렛트, 박스 데이터] 시트와 절대 혼용 금지.
    - 600박스: 1PLT당 8박스 / 파렛트 1,200×800×730mm / 패키징 1,200×800×1,460mm
    - 650박스: 1PLT당 20박스 / 파렛트 1,100×1,100×2,200mm
    - 1090박스: 1PLT당 4박스 / 파렛트 1,100×1,100×1,110mm / 패키징 1,100×1,100×2,220mm

17. **수출 컨테이너 선택 규칙**: '컨테이너', '20ft', '40ft' 관련 질문은
    혼합 조합(40ft+20ft)도 함께 제시하고 잔여 공간 최소 조합을 최적 추천.
    - 20ft: 최대 10PLT / 40ft: 최대 20PLT (파렛트 1.1×1.1m, 1단 적재)
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
        return self._call_with_max_tokens(prompt, max_tokens=2048)

    def _call_with_max_tokens(self, prompt: str, max_tokens: int = 2048) -> str:
        self._enforce_rate_limit()
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "stream": False,
            "max_tokens": max_tokens
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

    # 시트명 → 도메인 매핑
    SHEET_TO_DOMAIN = {
        "컨베어벨트 규격 데이터"         : "conveyor",
        "주름혹벨트 우든박스 사이즈 데이터": "sidewall",   # 주름혹벨트 전용
        "크롤러 러버트랙 규격 데이터"      : "crawler",
    }

    def __init__(self, vectorstore, llm, embeddings, qdrant_client):
        self.vectorstore = vectorstore
        self.llm = llm
        self.embeddings = embeddings
        self.qdrant_client = qdrant_client
        self.prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
        # 코드 → 시트명 매핑 캐시 (시작 시 Qdrant에서 빌드)
        self._code_sheet_map: dict = {}
        self._build_code_sheet_map()

    def _build_code_sheet_map(self):
        """
        Qdrant logistics_data에서 material_code 페이로드를 읽어
        {코드: sheet_name} 매핑 딕셔너리를 빌드.
        코드만으로 자재 종류(시트) 자동 판별에 사용.
        """
        try:
            offset = None
            batch_size = 500
            while True:
                result = self.qdrant_client.scroll(
                    collection_name=QDRANT_COLLECTION,
                    scroll_filter=models.Filter(
                        must=[models.FieldCondition(
                            key="material_code",
                            match=models.MatchAny(any=["*"])   # 존재하는 것만
                        )]
                    ) if False else None,   # 필터 없이 전체 스캔
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )
                points, next_offset = result
                for point in points:
                    code = point.payload.get("material_code") or \
                           point.payload.get("metadata", {}).get("material_code")
                    sheet = point.payload.get("sheet_name") or \
                            point.payload.get("metadata", {}).get("sheet_name", "")
                    if code and sheet:
                        self._code_sheet_map[str(code)] = sheet

                if next_offset is None or len(points) < batch_size:
                    break
                offset = next_offset

            logger.info(f"✅ 코드-시트 매핑 빌드 완료: {len(self._code_sheet_map)}개 코드")
        except Exception as e:
            logger.warning(f"코드-시트 매핑 빌드 실패 (fallback 사용): {e}")
            self._code_sheet_map = {}

    def _sheet_to_domain(self, sheet_name: str) -> Optional[str]:
        """시트명 → 도메인 변환"""
        for key, domain in self.SHEET_TO_DOMAIN.items():
            if key in sheet_name:
                return domain
        return None

    def _domain_from_code(self, code: str) -> Optional[str]:
        """코드만으로 도메인 판별 (매핑 캐시 사용)"""
        sheet = self._code_sheet_map.get(str(code))
        if sheet:
            return self._sheet_to_domain(sheet)
        return None
    
    @lru_cache(maxsize=100)
    def extract_material_code(self, query: str) -> Optional[str]:
        """자재코드(7자리) 추출 - 한글 앞뒤 경계도 처리"""
        patterns = [
            r'자재코드[:\s]*(\d{7})',
            r'코드[:\s]*(\d{7})',
            r'품번[:\s]*(\d{7})',
            # 숫자 앞뒤로 숫자가 없는 경우 (한글/공백/문장부호 포함)
            r'(?<![0-9])(\d{7})(?![0-9])',
        ]
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                return match.group(1)
        return None
    
    def keyword_search_optimized(self, material_code: str, limit: int = 5):
        """
        자재코드 필터 검색.
        1차: 최상위 material_code 필터 (data_loader 최신 버전)
        2차: metadata.material_code 필터 (구버전 호환)
        """
        points_found = []
        try:
            # 1차: 최상위 키
            result = self.qdrant_client.scroll(
                collection_name=QDRANT_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="material_code",
                                        match=MatchValue(value=material_code))]
                ),
                limit=limit, with_payload=True, with_vectors=False
            )
            points_found = result[0]
        except Exception as e:
            logger.warning(f"1차 코드 검색 실패: {e}")

        # 2차: metadata 중첩 키 (구버전)
        if not points_found:
            try:
                result = self.qdrant_client.scroll(
                    collection_name=QDRANT_COLLECTION,
                    scroll_filter=Filter(
                        must=[FieldCondition(key="metadata.material_code",
                                            match=MatchValue(value=material_code))]
                    ),
                    limit=limit, with_payload=True, with_vectors=False
                )
                points_found = result[0]
            except Exception as e:
                logger.warning(f"2차 코드 검색 실패: {e}")

        matched_docs = []
        for point in points_found:
            payload = point.payload
            matched_docs.append({
                'id'      : point.id,
                'content' : payload.get('page_content', ''),
                'metadata': payload.get('metadata', {}),
                'score'   : 1.0
            })

        logger.info(f"키워드 검색 [{material_code}]: {len(matched_docs)}개")
        return matched_docs
        
    def _detect_domain(self, query: str, keyword_doc_content: str = "") -> str:
        """
        질문 + 검색된 문서 내용을 기반으로 도메인 판별.
        자재코드가 있으면 코드-시트 매핑으로 우선 판별 (가장 정확).
        단, 운송방식 키워드가 함께 있으면 domestic 우선 적용.
        반환값: 'conveyor' | 'sidewall' | 'crawler' | 'export' | 'domestic' | 'driver_route' | 'general'
        """
        combined = query + " " + keyword_doc_content

        # ── 0순위: 국내 운송방식 키워드 — 자재코드 유무와 무관하게 최우선 ──
        # "출고", "운송방식", "직송", "화물", "택배" 가 있으면 물류팀 운영 규칙이 필요
        domestic_kw = ["운송방식", "직송", "화물", "택배", "출고", "국내 출고", "운송 방식",
                       "어떤 운송", "운반 방법", "배송 방법", "배송방법", "운반방법"]
        if any(k in query for k in domestic_kw):
            logger.info(f"운송방식 키워드 감지 → 도메인: domestic")
            return "domestic"

        # ── 1순위: 코드-시트 매핑으로 정확한 판별 ──────────────────────
        code = self.extract_material_code(query)
        if code:
            domain_from_code = self._domain_from_code(code)
            if domain_from_code:
                logger.info(f"코드 {code} → 도메인: {domain_from_code} (매핑 캐시)")
                return domain_from_code

        # ── 2순위: 키워드 기반 판별 ──────────────────────────────────────

        # 지입기사 납품 동선 도메인
        driver_kw = ["지입기사", "납품 동선", "동선", "기사 노선", "납품 노선", "배달 경로",
                     "김병일", "김영철", "이용구", "심효섭",
                     "부산기사", "중부기사", "서울기사",
                     "지입 기사", "납품경로", "납품코스"]
        if any(k in combined for k in driver_kw):
            return "driver_route"

        # 주름혹벨트 도메인 (컨베어보다 먼저 체크 - ME SW 패턴)
        sidewall_kw = ["주름혹", "sidewall", "SW ", "ME SW", "우든박스", "우드박스"]
        if any(k in combined for k in sidewall_kw):
            return "sidewall"

        # 컨베어벨트 도메인
        conveyor_kw = ["컨베어", "컨베이어", "직경", "롤", "NN", "EP", "포규격", "심체", "컨베어벨트"]
        if any(k in combined for k in conveyor_kw):
            return "conveyor"

        # 크롤러/러버트랙 도메인
        crawler_kw = ["크롤러", "러버트랙", "RT", "트랙", "배차", "몇 톤", "파렛트", "Rubber Track"]
        if any(k in combined for k in crawler_kw):
            return "crawler"

        # 수출 포장 도메인 (CBM/파렛트 계산 포함)
        export_kw = ["박스", "포장량", "컨테이너", "B01", "B02", "N18", "N19", "마대", "우든",
                     "CBM", "cbm", "Pallet", "파렛트", "전동수출", "수출 파렛트"]
        if any(k in combined for k in export_kw):
            return "export"

        return "general"

    def fetch_whole_docs(self, sheet_names: list, limit: int = 5):
        """WHOLE/QA 전략으로 저장된 특정 시트 문서를 페이로드 필터로 가져옴
        - 최상위 sheet_name 필터 우선, 없으면 metadata.sheet_name 시도 (Qdrant 버전 호환)
        """
        from langchain_core.documents import Document
        docs = []
        try:
            for sheet in sheet_names:
                points_found = []

                # 1차: 최상위 sheet_name 필터 (data_loader v2 이후)
                try:
                    result = self.qdrant_client.scroll(
                        collection_name=QDRANT_COLLECTION,
                        scroll_filter=Filter(
                            must=[FieldCondition(
                                key="sheet_name",
                                match=MatchValue(value=sheet)
                            )]
                        ),
                        limit=limit,
                        with_payload=True,
                        with_vectors=False
                    )
                    points_found = result[0]
                except Exception:
                    pass

                # 2차: metadata.sheet_name 필터 (구버전 인덱스 호환)
                if not points_found:
                    try:
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
                        points_found = result[0]
                    except Exception:
                        pass

                for point in points_found:
                    payload = point.payload
                    doc = Document(
                        page_content=payload.get('page_content', ''),
                        metadata=payload.get('metadata', {})
                    )
                    if doc.page_content:
                        docs.append((doc, 0.9))

                logger.info(f"fetch_whole_docs [{sheet}]: {len(points_found)}개 조회")

        except Exception as e:
            logger.warning(f"WHOLE 문서 보완 실패: {e}")
        return docs

    # 도메인별 보완 시트 매핑
    DOMAIN_SUPPLEMENT_SHEETS = {
        "conveyor"     : ["컨베어벨트 직경 산출 수식"],
        "sidewall"     : ["주름혹벨트 우든박스 사이즈 데이터"],
        "crawler"      : ["차량 데이터"],
        "domestic"     : ["물류팀 운영 규칙", "용차 차량 노선 데이터", "차량 데이터"],
        # export·general 모두 물류팀 운영 규칙 포함 — CBM/컨테이너/운임 계산 데이터 확보
        "export"       : ["수출 포장량 산출 수식", "포장량 산출 데이터", "물류팀 운영 규칙"],
        "driver_route" : ["지입 차량(기사) 노선 데이터"],
        "general"      : ["차량 데이터", "물류팀 운영 규칙"],
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

                # 코드-시트 매핑 우선, 없으면 문서 내용으로 도메인 판별
                first_doc_content = keyword_results[0].get('content', '')
                domain = self._detect_domain(query, first_doc_content)
                supplement_sheets = list(self.DOMAIN_SUPPLEMENT_SHEETS.get(domain, []))

                # ★ domestic 도메인: 자재코드 기반 도메인 시트도 추가 보완
                #   (운송방식 판단에는 물류팀 운영 규칙 + 자재 중량 데이터 모두 필요)
                if domain == "domestic":
                    code_domain = self._domain_from_code(material_code)
                    if code_domain:
                        extra_sheets = self.DOMAIN_SUPPLEMENT_SHEETS.get(code_domain, [])
                        for s in extra_sheets:
                            if s not in supplement_sheets:
                                supplement_sheets = [s] + supplement_sheets
                    logger.info(f"domestic 보완 시트 (자재+운송): {supplement_sheets}")

                if supplement_sheets:
                    whole_docs = self.fetch_whole_docs(supplement_sheets, limit=2)
                    results.extend(whole_docs)
                    logger.info(f"코드 검색: {len(keyword_results)}개 | 도메인: {domain} | 보완: {supplement_sheets} ({len(whole_docs)}개)")
                else:
                    logger.info(f"코드 검색: {len(keyword_results)}개 | 도메인: {domain} | 보완 없음")
                return results

            else:
                # Qdrant 필터 검색 실패 → 코드-시트 캐시로 도메인 판별 후 벡터 검색 보완
                domain_from_code = self._domain_from_code(material_code)
                if domain_from_code:
                    logger.warning(f"코드 {material_code} Qdrant 조회 실패 → 도메인 {domain_from_code}로 벡터 검색 보완")
                    supplement_sheets = list(self.DOMAIN_SUPPLEMENT_SHEETS.get(domain_from_code, []))
                    # ★ domestic 도메인이면 물류팀 운영 규칙도 추가
                    detected = self._detect_domain(query)
                    if detected == "domestic":
                        for s in self.DOMAIN_SUPPLEMENT_SHEETS.get("domestic", []):
                            if s not in supplement_sheets:
                                supplement_sheets.append(s)
                    if supplement_sheets:
                        whole_docs = self.fetch_whole_docs(supplement_sheets, limit=3)
                        results.extend(whole_docs)
                # 결과가 없으면 아래 벡터 검색으로 fallback

        try:
            vector_results = self.vectorstore.similarity_search_with_score(query, k=50)

            if len(vector_results) > 3:
                filtered_results = [(doc, score) for doc, score in vector_results if score >= 0.15]
            else:
                filtered_results = vector_results

            # 이미 results에 코드 기반 문서가 있으면 합산
            if results:
                existing = {doc.page_content[:50] for doc, _ in filtered_results}
                for doc, score in results:
                    if doc.page_content[:50] not in existing:
                        filtered_results.insert(0, (doc, score))
                        existing.add(doc.page_content[:50])

            domain = self._detect_domain(query)

            # 자재코드 질문인데 벡터 결과만 있는 경우 → 해당 도메인 시트 문서 강제 보완
            if material_code and domain not in ("driver_route", "general"):
                supplement_sheets = self.DOMAIN_SUPPLEMENT_SHEETS.get(domain, [])
                if supplement_sheets:
                    existing = {doc.page_content[:50] for doc, _ in filtered_results}
                    extra = self.fetch_whole_docs(supplement_sheets, limit=2)
                    for doc, score in extra:
                        if doc.page_content[:50] not in existing:
                            filtered_results.append((doc, score))
                    logger.info(f"코드 벡터 fallback 보완: 도메인={domain}, +{len(extra)}개")

            # 지입기사 납품 동선 질문이면 노선 전체 문서를 강제 보완
            if domain == "driver_route":
                driver_docs = self.fetch_whole_docs(["지입 차량(기사) 노선 데이터"], limit=10)
                if driver_docs:
                    filtered_results = driver_docs
                    logger.info(f"지입기사 노선 전용 컨텍스트: {len(driver_docs)}개")
                else:
                    driver_kw = ["지입", "기사", "노선", "납품", "동선"]
                    driver_filtered = [
                        (doc, score) for doc, score in filtered_results
                        if any(kw in doc.page_content for kw in driver_kw)
                        or "지입 차량" in doc.metadata.get("sheet_name", "")
                    ]
                    if driver_filtered:
                        filtered_results = driver_filtered
                        logger.info(f"지입기사 벡터 결과 필터링: {len(driver_filtered)}개")
                    else:
                        logger.warning("지입기사 노선 문서 조회 실패 — 벡터 검색 전체 결과 사용")

            logger.info(f"벡터 검색 결과 확보: {len(filtered_results)}개")
            return filtered_results
        except Exception as e:
            logger.error(f"벡터 검색 실패: {e}")
            return results if results else []
          
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
    """LaTeX 변환, 숫자 점수 제거, 마크다운 특수문자 정리"""
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

    # ── 마크다운 특수문자 정리 ──────────────────────────────────────────
    # **(답변)** 같이 답변 구조 태그로 쓰인 ** 제거
    # 단, 표(|...|) 안에 있는 **bold**는 앱에서 HTML로 변환되므로 유지
    lines = answer.split('\n')
    cleaned = []
    for line in lines:
        # 표 행은 건드리지 않음
        if line.strip().startswith('|'):
            cleaned.append(line)
            continue
        # 헤더(##) 줄도 유지 (md_to_html_answer가 처리)
        if re.match(r'^#{1,3}\s', line.strip()):
            cleaned.append(line)
            continue
        # **(레이블)** 패턴: 줄 맨 앞에 오는 구조 태그 형태 제거
        # 예) **(답변)**, **(핵심)**, **(요약)** 등
        line = re.sub(r'^\s*\*\*\([^)]+\)\*\*\s*', '', line)
        # 줄 중간에 **텍스트:** 형태도 텍스트만 남김 (콜론 포함)
        line = re.sub(r'\*\*([^*]+):\*\*', r'\1:', line)
        # 나머지 모든 **텍스트** → 텍스트만 남김 (** 특수문자 화면 노출 방지)
        # 표/헤더 줄은 이미 위에서 continue 처리됐으므로 여기선 일반 텍스트만 대상
        line = re.sub(r'\*\*([^*\n]+)\*\*', r'\1', line)
        cleaned.append(line)
    answer = '\n'.join(cleaned)

    # 연속 빈 줄 2개 이상 → 1개로 압축
    answer = re.sub(r'\n{3,}', '\n\n', answer)

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


def _format_driver_route_answer(query: str, context_text: str) -> str:
    """
    지입기사 납품 동선 답변 - Python 직접 포맷팅 (LLM 미사용).

    기능:
    (1) 동일 노선 요일 자동 묶기 (월~금 → "월~금 (매일)")
    (2) 서울 기사(이용구/심효섭) 격주 노선 교대
        - 이번 주 운행 기사 노선 먼저, 다음 주 기사 노선은 아래에 참고용 표시
    (3) "현재 위치/지금 어디" 질문: 현재 시각으로 예상 위치 계산
    """
    import re as _re
    from datetime import date as _date, datetime as _dt

    # ── 0. 현재 위치 조회 요청 감지 ─────────────────────────────────────
    LOCATION_KW = ["현재 위치", "지금 어디", "현재 어디", "어디 있", "몇 시에", "지금 위치",
                   "예상 위치", "현재위치", "지금쯤", "어디쯤"]
    is_location_query = any(k in query for k in LOCATION_KW)

    # ── 1. 소속/이름 범위 감지 ────────────────────────────────────────────
    scope_busan   = any(k in query for k in ["부산", "부산공장", "부산 기사"])
    scope_seoul   = any(k in query for k in ["서울", "중부", "중부물류", "수도권"])
    specific_name = next((n for n in ["김병일", "김영철", "이용구", "심효섭"] if n in query), None)

    # ── 2. 격주 운행 판별 ────────────────────────────────────────────────
    # 기준: 2025년 1월 6일(월) = 이용구 노선 운행 1주차
    # 홀수 주(0,2,4...) → 이용구 노선 운행주, 짝수 주(1,3,5...) → 심효섭 노선 운행주
    _BASE_MONDAY      = _date(2025, 1, 6)
    _today            = _date.today()
    _week_elapsed     = ((_today - _BASE_MONDAY).days) // 7
    _this_week_driver = "이용구" if _week_elapsed % 2 == 0 else "심효섭"
    _next_week_driver = "심효섭" if _week_elapsed % 2 == 0 else "이용구"

    # ── 3. context_text 파싱 ─────────────────────────────────────────────
    driver_blocks: dict = {}
    current_driver = None
    for line in context_text.split('\n'):
        h2 = _re.match(r'^##\s+(.+)', line.strip())
        if h2:
            current_driver = h2.group(1).strip()
            driver_blocks[current_driver] = []
            continue
        if current_driver and line.strip().startswith('|') and '---' not in line:
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if len(cells) >= 2 and cells[0] not in ('요일', ''):
                driver_blocks[current_driver].append((cells[0], cells[1]))

    if not driver_blocks:
        return context_text

    # ── 4. 기본 정보 ─────────────────────────────────────────────────────
    BUSAN_DRIVERS = ["김병일", "김영철"]
    SEOUL_DRIVERS = ["이용구", "심효섭"]
    DAY_ORDER     = {"월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3, "금요일": 4}
    DRIVER_INFO   = {
        "김병일": {"tel": "010-3587-4581", "car": "3.5톤 카고", "area": "부산·경남권"},
        "김영철": {"tel": "010-7123-6231", "car": "1톤 카고",   "area": "울산·마산·창원권"},
        "이용구": {"tel": "010-9263-4190", "car": "2.5톤 카고", "area": "서울·경기·인천권"},
        "심효섭": {"tel": "010-5291-6593", "car": "2.5톤 카고", "area": "서울 도심권"},
    }

    def _get_info(name_key: str) -> dict:
        for k, v in DRIVER_INFO.items():
            if k in name_key:
                return {"short": k, **v}
        return {"short": name_key, "tel": "-", "car": "-", "area": "-"}

    def _should_include(driver_key: str) -> bool:
        short = _get_info(driver_key)["short"]
        if specific_name:
            return specific_name in short
        if scope_busan and not scope_seoul:
            return short in BUSAN_DRIVERS
        if scope_seoul and not scope_busan:
            return short in SEOUL_DRIVERS
        return True

    # ── 5. 동일 노선 요일 묶기 ───────────────────────────────────────────
    def _compress_routes(routes: list) -> list:
        if not routes:
            return []
        sorted_r = sorted(routes, key=lambda x: DAY_ORDER.get(x[0], 99))
        dest_map: dict = {}
        for day, dest in sorted_r:
            key = _re.sub(r'\s+', ' ', dest.strip())
            dest_map.setdefault(key, []).append(day)

        compressed = []
        for dest_key, days in dest_map.items():
            days_s = sorted(days, key=lambda d: DAY_ORDER.get(d, 99))
            idxs   = [DAY_ORDER.get(d, 99) for d in days_s]
            consec = all(idxs[i+1]-idxs[i]==1 for i in range(len(idxs)-1))

            if len(days_s) == 5:
                label = "**월~금 (매일)**"
            elif consec and len(days_s) >= 3:
                label = f"**{days_s[0][:1]}~{days_s[-1][:1]}요일**"
            elif consec and len(days_s) == 2:
                label = f"**{'·'.join(d[:1] for d in days_s)}요일**"
            else:
                label = "**" + "·".join(d[:1]+"요일" for d in days_s) + "**"

            compressed.append((label, dest_key))

        def _first_idx(item):
            lbl = item[0].replace("*","")
            for d, i in DAY_ORDER.items():
                if d[:1] in lbl:
                    return i
            return 99
        compressed.sort(key=_first_idx)
        return compressed

    # ── 6. 납품 동선 포맷팅 ──────────────────────────────────────────────
    def _is_sequential(dest_raw: str) -> bool:
        """
        납품처들이 순차 납품인지 분기(주문건수에 따라 변동)인지 판별.
        시간이 모두 다르고 단조 증가하면 순차, 동일 시간 존재 시 분기.
        """
        items = [s.strip() for s in dest_raw.replace('\n',' / ').split(' / ') if s.strip()]
        times = []
        for item in items:
            m = _re.search(r'\((\d{1,2})시(\d{1,2})?분?\)', item)
            if m:
                times.append(int(m.group(1))*60 + int(m.group(2) or 0))
        if len(times) < 2:
            return True
        return len(set(times)) == len(times) and times == sorted(times)

    def _fmt_dest(dest_raw: str) -> str:
        """
        납품 동선 포맷팅.
        - 순차 납품: ① ② ③ ... 번호로 나열
        - 분기 납품: 🔀 A / B / C 형태로 표시 (주문건수에 따라 변동)
        """
        items = [s.strip() for s in dest_raw.replace('\n',' / ').split(' / ') if s.strip()]
        if not items:
            return dest_raw

        if _is_sequential(dest_raw):
            # 순차 납품 → 번호 나열
            return "<br>".join(f"**{i}.** {s}" for i, s in enumerate(items, 1))
        else:
            # 분기 납품 → 🔀 A / B / C 형태
            # 같은 시간대끼리 그룹핑해서 묶기
            groups = []
            current_group = [items[0]]
            for i in range(1, len(items)):
                # 앞 아이템과 시간이 같으면 같은 그룹
                def get_min(s):
                    m = _re.search(r'\((\d{1,2})시(\d{1,2})?분?\)', s)
                    return int(m.group(1))*60+int(m.group(2) or 0) if m else -1
                if get_min(items[i]) == get_min(items[i-1]):
                    current_group.append(items[i])
                else:
                    groups.append(current_group)
                    current_group = [items[i]]
            groups.append(current_group)

            parts_out = []
            for g in groups:
                if len(g) == 1:
                    parts_out.append(f"**{len(parts_out)+1}.** {g[0]}")
                else:
                    parts_out.append("🔀 " + "  /  ".join(g) + " _(주문건수에 따라 변동)_")
            return "<br>".join(parts_out)

    # ── 7. ★ 현재 예상 위치 계산 ────────────────────────────────────────
    def _parse_time_stops(dest_raw: str) -> list:
        """
        납품 동선 문자열에서 [(거래처명, HH, MM), ...] 파싱.
        실제 context_text 형태: " / " 구분자 한 줄 문자열
        "(서울)흥진사(10시)" → ("흥진사", 10, 0)
        "(서울)명진(10시5분)" → ("명진", 10, 5)
        """
        # " / " 또는 줄바꿈으로 분리
        raw_clean = dest_raw.replace('\r\n', ' / ').replace('\n', ' / ').replace('\r', '')
        items     = [s.strip() for s in raw_clean.split(' / ') if s.strip()]
        stops = []
        for item in items:
            m = _re.search(
                r'\(([^)]+)\)([^(]+)\((\d{1,2})시(\d{1,2})?분?\)',
                item
            )
            if m:
                name = m.group(2).strip()
                hh   = int(m.group(3))
                mm   = int(m.group(4)) if m.group(4) else 0
                stops.append((name, hh, mm))
        return stops

    def _estimate_location(driver_name: str, routes: list) -> str:
        """
        현재 시각 기준으로 기사 예상 위치 계산.
        오늘 요일의 노선에서 현재 시각과 납품 예정 시각을 비교.
        """
        now        = _dt.now()
        weekday    = now.weekday()   # 0=월 ~ 4=금
        day_names  = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"]
        today_name = day_names[weekday]

        # 주말
        if weekday >= 5:
            return f"⛔ 오늘은 **{today_name}**입니다. {driver_name} 기사는 주말에 운행하지 않습니다."

        # 오늘 요일 노선 찾기
        today_route = next((dest for day, dest in routes if day == today_name), None)
        if not today_route:
            return f"오늘({today_name}) {driver_name} 기사의 노선 데이터를 찾을 수 없습니다."

        stops = _parse_time_stops(today_route)
        if not stops:
            return f"{driver_name} 기사의 오늘 노선에서 시간 데이터를 파싱할 수 없습니다."

        now_min = now.hour * 60 + now.minute
        first_stop_min = stops[0][1] * 60 + stops[0][2]
        last_stop_min  = stops[-1][1] * 60 + stops[-1][2]

        # 출발 전
        if now_min < first_stop_min:
            diff = first_stop_min - now_min
            return (
                f"🕐 현재 시각 **{now.hour:02d}:{now.minute:02d}** 기준\n\n"
                f"아직 출발 전입니다. 첫 납품지 **{stops[0][0]}** 도착 예정까지 약 **{diff}분** 남았습니다."
            )

        # 마지막 납품 완료 후
        if now_min > last_stop_min + 30:
            return (
                f"🕐 현재 시각 **{now.hour:02d}:{now.minute:02d}** 기준\n\n"
                f"오늘 납품이 완료되었을 것으로 예상됩니다. "
                f"마지막 납품지 **{stops[-1][0]}** 도착 예정 시각은 **{stops[-1][1]:02d}:{stops[-1][2]:02d}**였습니다."
            )

        # 현재 납품 중
        location_msg = ""
        for i, (name, hh, mm) in enumerate(stops):
            stop_min = hh * 60 + mm
            if now_min == stop_min:
                location_msg = f"📍 **{name}** 납품 중 (예정 도착 시각: **{hh:02d}:{mm:02d}**)"
                break
            if now_min < stop_min:
                if i == 0:
                    location_msg = f"🚗 이동 중 → **{name}** 도착 예정 **{hh:02d}:{mm:02d}** (약 {stop_min - now_min}분 후)"
                else:
                    prev_name, prev_hh, prev_mm = stops[i-1]
                    location_msg = (
                        f"🚗 **{prev_name}** 납품 완료 후 **{name}** 이동 중\n"
                        f"  → {name} 도착 예정 **{hh:02d}:{mm:02d}** (약 {stop_min - now_min}분 후)"
                    )
                break

        if not location_msg:
            location_msg = f"📍 **{stops[-1][0]}** 근처에 있을 것으로 예상됩니다."

        # 전체 오늘 동선 요약
        route_summary = "\n".join(
            f"  {'✅' if (h*60+m) <= now_min else '⏳'} **{h:02d}:{m:02d}** {n}"
            for n, h, m in stops
        )

        return (
            f"🕐 현재 시각 **{now.hour:02d}:{now.minute:02d}** ({today_name}) 기준\n\n"
            f"### {driver_name} 기사 예상 현재 위치\n"
            f"{location_msg}\n\n"
            f"**오늘({today_name}) 전체 동선:**\n{route_summary}\n\n"
            f"> ⚠️ 예상 위치는 납품 시각 기준 추정값입니다. 실제 위치는 기사에게 직접 확인해 주세요."
        )

    # ── 8. 현재 위치 질문 처리 ───────────────────────────────────────────
    if is_location_query:
        target_name = specific_name
        if not target_name:
            # 이름 미지정 시 서울 기사이면 이번 주 운행자, 부산이면 안내
            if scope_seoul and not scope_busan:
                target_name = _this_week_driver
            elif scope_busan and not scope_seoul:
                return "현재 위치 조회는 특정 기사 이름을 포함해 질문해 주세요. (예: '김병일 기사 지금 어디?')"
            else:
                return "현재 위치를 조회할 기사 이름을 포함해 질문해 주세요. (예: '심효섭 기사 지금 어디?')"

        # target 기사의 routes 찾기
        target_routes = None
        for dk, rv in driver_blocks.items():
            if target_name in dk:
                target_routes = rv
                break

        if target_routes is None:
            return f"{target_name} 기사의 노선 데이터를 찾을 수 없습니다."

        # 서울 기사: 이번 주 운행 여부 확인
        if target_name in SEOUL_DRIVERS:
            if target_name != _this_week_driver:
                return (
                    f"⏸️ **{target_name} 기사**는 이번 주 운행 주간이 아닙니다.\n\n"
                    f"이번 주 서울 운행은 **{_this_week_driver} 기사** 담당입니다.\n"
                    f"다음 주부터 **{target_name} 기사** 노선으로 변경됩니다.\n\n"
                    f"📞 확인이 필요하면 **{target_name} 기사 ({DRIVER_INFO[target_name]['tel']})**에게 직접 문의해 주세요."
                )

        return _estimate_location(target_name, target_routes)

    # ── 9. 일반 노선 조회 답변 ───────────────────────────────────────────
    lines = []

    # 도입 멘트
    if specific_name:
        lines.append(f"**{specific_name} 기사** 납품 동선 정보입니다.\n")
    elif scope_busan and not scope_seoul:
        lines.append("**부산공장 지입기사** 납품 동선 정보입니다.\n")
    elif scope_seoul and not scope_busan:
        lines.append("**서울(중부물류센터) 지입기사** 납품 동선 정보입니다.\n")
    else:
        lines.append("지입기사 전원의 납품 동선 정보입니다.\n")

    groups = []
    if not (scope_seoul and not scope_busan):
        groups.append(("🚚 부산공장 지입기사", BUSAN_DRIVERS))
    if not (scope_busan and not scope_seoul):
        groups.append(("🚌 서울(중부물류센터) 지입기사", SEOUL_DRIVERS))

    for group_title, name_list in groups:
        is_seoul_group = (name_list == SEOUL_DRIVERS)
        group_drivers  = [
            (dk, dv) for dk, dv in driver_blocks.items()
            if any(n in dk for n in name_list) and _should_include(dk)
        ]
        if not group_drivers:
            continue

        lines.append(f"## {group_title}\n")

        # ── 서울 기사: 이번 주 / 다음 주 노선 배너 ──────────────────────
        if is_seoul_group and not specific_name:
            lines.append(
                f"> 🗓️ **이번 주 운행 노선: {_this_week_driver} 기사**  "
                f"｜  다음 주: {_next_week_driver} 기사\n"
                f"> 두 기사는 격주로 노선을 교대하며 **둘 다 월~금 매일 운행**합니다.\n"
            )

        # ── 이번 주 운행 기사 먼저, 다음 주 기사는 뒤에 ─────────────────
        if is_seoul_group and not specific_name:
            # 이번 주 기사 먼저 정렬
            group_drivers = sorted(
                group_drivers,
                key=lambda x: (0 if _this_week_driver in x[0] else 1)
            )

        for driver_key, routes in group_drivers:
            info  = _get_info(driver_key)
            short = info["short"]

            # 이번 주 / 다음 주 배지
            if is_seoul_group and not specific_name:
                if short == _this_week_driver:
                    week_tag = "  🟢 **이번 주 운행 노선**"
                else:
                    week_tag = "  🔵 다음 주 운행 노선"
            else:
                week_tag = ""

            lines.append(f"### {short} 기사{week_tag}")
            lines.append(
                f"- 📱 **{info['tel']}**  |  🚛 {info['car']}  |  📍 {info['area']}"
            )
            lines.append("- 운행: **월~금 (주 5일) 매일 운행**\n")

            if routes:
                compressed = _compress_routes(routes)
                lines.append("| 운행 요일 | 납품 동선 |")
                lines.append("|:---------:|:---------|")
                for day_label, dest_raw in compressed:
                    lines.append(f"| {day_label} | {_fmt_dest(dest_raw)} |")
                lines.append("")
            else:
                lines.append("_동선 데이터 없음_\n")

    # 특이사항
    if not specific_name:
        lines.append("---")
        lines.append("**💡 운행 특이사항**")
        if not (scope_seoul and not scope_busan):
            lines.append(
                "- 부산공장 기사: 미성폴리머(김해)/신항 등 추가 운행은 첫 운행(오전)에만 가능, 점심 이후 불가"
            )
        if not (scope_busan and not scope_seoul):
            lines.append(
                f"- 서울 기사: 이용구·심효섭 기사가 **격주로 노선 교대** 운행 "
                f"(이번 주: **{_this_week_driver}** 기사 노선 / 다음 주: {_next_week_driver} 기사 노선)"
            )
        lines.append("")

    lines.append("📞 납품 일정 변경·추가 문의는 **물류팀 담당자**에게 연락해 주세요.")
    return "\n".join(lines)



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
        search_k = 15

    # 웹서치를 허용할 명시적 키워드 (사내 데이터에 없는 외부 정보가 필요한 경우)
    WEB_ALLOWED_KW = [
        "최신", "뉴스", "시세", "환율", "날씨", "법률", "규정", "관세",
        "HS코드", "incoterms", "인코텀즈", "선적 서류", "수출 서류",
        "B/L", "invoice", "packing list", "원산지증명", "세관"
    ]
    _allow_web = any(kw.lower() in query.lower() for kw in WEB_ALLOWED_KW)

    try:
        filtered_docs = rag_chain.hybrid_search(query, k=search_k)

        if not filtered_docs:
            # 로컬 문서 없을 때: 웹서치 허용 키워드 있으면 웹서치, 없으면 LLM 자체 지식으로 답변
            if _allow_web:
                use_web_search = True
            else:
                # LLM 자체 지식으로 답변 시도
                fallback_prompt = rag_chain.prompt_template.format(
                    context="관련 내부 데이터가 없습니다. 일반 물류 지식을 바탕으로 답변하세요.",
                    input=query,
                    history_context=history_context if history_context else "없음",
                    conversation_context=conversation_context if conversation_context else "없음"
                )
                try:
                    answer = rag_chain.llm._call(fallback_prompt)
                except Exception:
                    answer = "해당 정보를 내부 데이터에서 찾을 수 없습니다. 담당자에게 직접 문의해 주세요."
        else:
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

            _domain_for_limit = rag_chain._detect_domain(query)
            _ctx_limit = 8000 if _domain_for_limit == "driver_route" else 4000
            if len(context_text) > _ctx_limit:
                context_text = context_text[:_ctx_limit] + "\n..."

            if is_table_request:
                has_table = True

            # ── driver_route: Python 직접 포맷팅 ──
            if _domain_for_limit == "driver_route":
                answer = _format_driver_route_answer(query, context_text)
                has_table = True
            else:
                formatted_prompt = rag_chain.prompt_template.format(
                    context=context_text,
                    input=query,
                    history_context=history_context if history_context else "없음",
                    conversation_context=conversation_context if conversation_context else "없음"
                )
                answer = rag_chain.llm._call(formatted_prompt)

            if "|" in answer and "---" in answer:
                has_table = True

            # 웹서치 전환 조건: 답변이 완전히 비어있고 + 웹허용 키워드 있을 때만
            if (not answer or len(answer.strip()) < 10) and _allow_web:
                use_web_search = True

    except Exception as e:
        import traceback
        logger.error(f"RAG 검색/답변 실패: {e}\n{traceback.format_exc()}")
        # 예외 발생 시에도 웹서치 허용 키워드 없으면 웹서치 건너뜀
        if _allow_web:
            use_web_search = True
        else:
            answer = "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
    
    # 웹 검색 (WEB_ALLOWED_KW에 해당하는 질문만 여기 도달)
    if use_web_search:
        logger.info(f"🌐 웹서치 발동: '{query[:40]}' (허용 키워드 매칭)")

        # driver_route는 Python 포맷팅으로 처리되므로 여기 도달하면 안 됨 (안전망)
        _domain_check = rag_chain._detect_domain(query)
        if _domain_check == "driver_route":
            _test_docs = rag_chain.fetch_whole_docs(["지입 차량(기사) 노선 데이터"], limit=1)
            if _test_docs:
                return (
                    "지입기사 납품 동선 데이터는 찾았으나 답변 생성 중 오류가 발생했습니다.\n\n"
                    "잠시 후 다시 시도해 주세요.",
                    [], False
                )
            else:
                return (
                    "지입기사 납품 동선 데이터를 Qdrant에서 찾을 수 없습니다.\n\n"
                    "`python data_loader.py`로 재인덱싱 후 다시 질문해 주세요.",
                    [], False
                )

        web_context = search_ddg(query)
        sources = [{'name': 'Web Search', 'score': 0.5, 'page': 'N/A'}]
        
        if web_context:
            enhanced_prompt = f"""당신은 DRB 물류 전문 AI 어시스턴트입니다.
아래 웹 검색 결과를 참고하여 질문에 답변하세요.
내부 데이터에 없는 내용이므로 웹 검색 결과를 바탕으로 친절하게 안내하세요.

[웹 검색 결과]
{web_context}

[질문]
{query}

{"⚠️ 표 형식으로 작성하세요." if is_table_request else ""}

답변:
"""
            try:
                orig_timeout = rag_chain.llm.timeout
                rag_chain.llm.timeout = 120
                answer = rag_chain.llm._call_with_max_tokens(enhanced_prompt, max_tokens=3000)
                rag_chain.llm.timeout = orig_timeout
                answer += "\n\n🌐 웹 검색 기반"
                if "|" in answer and "---" in answer:
                    has_table = True
            except Exception as e:
                logger.error(f"웹서치 LLM 호출 실패: {e}")
                answer = "답변 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."
        else:
            answer = "관련 정보를 찾을 수 없습니다. 담당자에게 직접 문의해 주세요."
    
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
    
def _calc_loadable_plt(plt_w: float, plt_l: float, car_w: float, car_l: float) -> int:
    """
    파렛트(plt_w × plt_l)를 차량 적재함(car_w × car_l)에
    가로·세로 두 방향 + 혼합 배열로 최대 몇 개 올릴 수 있는지 계산. 단위: m
    """
    best = 0
    orientations = [(plt_w, plt_l), (plt_l, plt_w)]

    # 단일 방향
    for pw, pl in orientations:
        if pw <= car_w:
            cols = int(car_w / pw)
            rows = int(car_l / pl)
            best = max(best, cols * rows)

    # 혼합 배열: 앞 구간 방향1, 나머지 구간 방향2
    for pw1, pl1 in orientations:
        for pw2, pl2 in orientations:
            if (pw1, pl1) == (pw2, pl2):
                continue
            cols1 = int(car_w / pw1) if pw1 <= car_w else 0
            cols2 = int(car_w / pw2) if pw2 <= car_w else 0
            if cols1 == 0 or cols2 == 0:
                continue
            for n1 in range(1, int(car_l / pl1) + 1):
                rem = car_l - n1 * pl1
                if rem < 0:
                    break
                n2 = int(rem / pl2)
                best = max(best, cols1 * n1 + cols2 * n2)

    return best


def get_db_transport_advice(total_pallets: float, total_weight_kg: float = 0.0,
                             plt_w: float = 1.1, plt_l: float = 1.1):
    """
    차량 데이터 WHOLE 문서를 파싱해 최적 차량 추천.
    ─ 1순위: 파렛트 실물 크기(plt_w × plt_l)를 차량 적재함에 실제 배열 가능한 수량으로 판단
    ─ 2순위: 중량은 참고용(weight_ok 플래그) — 경고 표시용으로만 사용
    plt_w, plt_l : 파렛트 실제 가로·세로 (m), 기본값 1100×1100mm
    """
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
        lowbed_entry = None
        for line in content.split('\n'):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 4:
                continue
            name = parts[0]
            if not name or '톤수' in name or name.startswith('[') or '특이사항' in name or '높이' in name:
                continue

            is_lowbed = any(kw in name for kw in ('로브이', 'Low-v', 'Low-bed', '로베드', 'low-bed', 'low-v'))
            if is_lowbed:
                nums_lb = re.findall(r'[\d.]+', parts[1]) if len(parts) >= 2 else []
                lowbed_entry = {
                    "name"          : name,
                    "spec"          : "높이 2.6m 이상 제품 전용 특수차량",
                    "max_plt"       : 999,
                    "max_weight_ton": float(nums_lb[-1]) if nums_lb else None,
                    "weight_ok"     : True,
                    "is_lowbed"     : True,
                }
                continue

            try:
                length = float(re.search(r'([\d.]+)m', parts[2]).group(1))
                width  = float(re.search(r'([\d.]+)m', parts[3]).group(1))
            except Exception:
                continue

            max_weight_ton = None
            if len(parts) >= 2:
                nums = re.findall(r'[\d.]+', parts[1])
                if nums:
                    max_weight_ton = float(nums[-1])

            # ── 핵심: 파렛트 실물 크기로 실제 배열 가능 수량 계산 ──────────
            max_plt = _calc_loadable_plt(plt_w, plt_l, width, length)

            if max_plt < total_pallets:
                continue  # 부피상 적재 불가 → 후보 제외

            weight_ok = True
            if total_weight_ton > 0 and max_weight_ton is not None:
                weight_ok = total_weight_ton <= max_weight_ton

            candidates.append({
                "name"          : name,
                "spec"          : f"길이 {length}m / 폭 {width}m",
                "max_plt"       : max_plt,
                "max_weight_ton": max_weight_ton,
                "weight_ok"     : weight_ok,
                "is_lowbed"     : False,
            })

        if not candidates:
            return None

        # ── 우선순위 선정 로직 ────────────────────────────────────────────
        # 1그룹(ok_both): PLT 수 OK + 중량 OK  → 이 중 가장 작은 차량
        # 2그룹(ok_vol) : PLT 수 OK + 중량 초과 → 불가피 시 사용, weight_ok=False 경고
        ok_both = [c for c in candidates if c['weight_ok']]
        ok_vol  = [c for c in candidates if not c['weight_ok']]

        if ok_both:
            # PLT 수 기준으로 가장 작은 차량 (중량도 만족하는 후보 중)
            return sorted(ok_both, key=lambda x: x['max_plt'])[0]
        elif ok_vol:
            # 중량 초과 차량만 남았을 때: 그나마 가장 작은 것 추천 + 경고
            logger.warning("중량 OK 차량 없음 → 부피 기준 차량 추천 (중량 경고 표시)")
            return sorted(ok_vol, key=lambda x: x['max_plt'])[0]
        else:
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