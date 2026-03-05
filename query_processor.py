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
PROMPT_TEMPLATE = """당신은 물류 계산 전문가입니다.
사용자의 질문에 '몇 박스', '산출', '계산' 등의 키워드가 포함되면 반드시 다음 단계를 따르세요.

1. <컨텍스트>에서 [수출 포장량 산출 가이드] 또는 [산출 수식] 문구를 먼저 찾으세요.
2. 가이드에 적힌 변수($A$, $B$, $C$, $W$)를 질문에서 추출하세요.
   - 예: N18은 자재그룹($C$), 3600KG은 중량($W$)입니다.
3. '포장량 산출 데이터' 표에서 조건에 맞는 '단위 무게(U)'를 찾으세요.
4. 공식(W / U)에 따라 계산 과정을 보여주고 최종 박스 수를 답하세요.
5. 질문과 관련 없는 단순 규격 데이터는 답변에서 제외하세요.

<컨텍스트>
{context}
</context>

질문: {input}

답변 규칙:
1. '총 몇 명인가?'와 같은 수량 질문에는 context에 있는 모든 항목을 하나씩 확인하여 정확한 합계를 구하세요.
2. 데이터가 나열되어 있다면 누락 없이 모두 언급하세요. '등', '외 n명'으로 생략하지 마세요.
3. 만약 정보가 여러 문서에 나뉘어 있다면 이를 통합해서 설명하세요.
4. 표 형식으로 정리할 수 있는 데이터는 반드시 Markdown 표를 사용하세요.
"""

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
            msg['From'] = self.email_from
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
    
    def _create_html_email(self, feedback_data: Dict) -> str:
        """HTML 형식의 이메일 본문 생성"""
        query = feedback_data.get('query', 'N/A')
        answer = feedback_data.get('answer', 'N/A')
        timestamp = feedback_data.get('timestamp', 'N/A')
        sources = feedback_data.get('sources', [])
        
        # 답변을 100자로 제한
        answer_preview = answer[:5000] + "..." if len(answer) > 100 else answer
        
        # 출처 정보 포맷팅
        sources_html = ""
        if sources:
            sources_list = []
            for idx, src in enumerate(sources[:3], 1):
                src_name = src.get('name', 'Unknown')
                src_score = src.get('score', 0)
                sources_list.append(f"<li>{src_name} (점수: {src_score:.3f})</li>")
            sources_html = "<ul>" + "".join(sources_list) + "</ul>"
        else:
            sources_html = "<p>출처 없음</p>"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    border-radius: 10px 10px 0 0;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                }}
                .content {{
                    background: #f8f9fa;
                    padding: 30px;
                    border-radius: 0 0 10px 10px;
                    border: 1px solid #e9ecef;
                }}
                .info-box {{
                    background: white;
                    padding: 20px;
                    margin: 15px 0;
                    border-radius: 8px;
                    border-left: 4px solid #dc3545;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .info-box h3 {{
                    margin-top: 0;
                    color: #dc3545;
                    font-size: 16px;
                }}
                .info-box p {{
                    margin: 10px 0;
                    color: #495057;
                }}
                .label {{
                    font-weight: bold;
                    color: #6c757d;
                    display: inline-block;
                    min-width: 80px;
                }}
                .timestamp {{
                    color: #6c757d;
                    font-size: 14px;
                    margin-top: 20px;
                    text-align: right;
                }}
                ul {{
                    margin: 10px 0;
                    padding-left: 20px;
                }}
                li {{
                    margin: 5px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #dee2e6;
                    color: #6c757d;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>👎 부정 피드백 알림</h1>
                <p>DRB 물류 AI 챗봇 - 답변 품질 개선 필요</p>
            </div>
            
            <div class="content">
                <div class="info-box">
                    <h3>📝 사용자 질문</h3>
                    <p>{query}</p>
                </div>
                
                <div class="info-box">
                    <h3>🤖 AI 답변 (미리보기)</h3>
                    <p>{answer_preview}</p>
                </div>
                
                <div class="info-box">
                    <h3>📚 참고 출처</h3>
                    {sources_html}
                </div>
                
                <div class="timestamp">
                    ⏰ 피드백 시각: {timestamp}
                </div>
                
                <div class="footer">
                    <p>이 메일은 bad_feedback_history 컬렉션 업데이트 시 자동으로 발송됩니다.</p>
                    <p>답변 품질 개선을 위해 검토가 필요합니다.</p>
                </div>
            </div>
        </body>
        </html>
        """       
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
                
                return results
        
        try:
            vector_results = self.vectorstore.similarity_search_with_score(query, k=50)
            
            # 무조건적인 0.25 필터링 대신, 검색 결과의 상위 순위를 보존
            # 결과가 충분히 있다면 하위 점수만 필터링
            if len(vector_results) > 3:
                filtered_results = [(doc, score) for doc, score in vector_results if score >= 0.15]
            else:
                filtered_results = vector_results # 결과가 적으면 일단 모두 전달
                
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
    
    def save_bad_feedback(self, query: str, answer: str, sources: List[Dict]):
        """
        부정 피드백 저장 + 이메일 알림 발송
        
        bad_feedback_history 컬렉션이 업데이트될 때마다 자동으로 이메일 전송
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
                "feedback_type": "bad"
            }
            
            # Qdrant에 저장
            self.client.upsert(
                collection_name=self.bad_collection,
                points=[PointStruct(id=feedback_id, vector=query_vector, payload=metadata)]
            )
            
            logger.info(f"💾 부정 피드백 저장: {query[:30]}...")
            
            # 이메일 알림 발송 (별도 스레드로 비동기 처리)
            if self.email_notifier and self.email_notifier.enabled:
                feedback_data = {
                    "query": query,
                    "answer": answer,
                    "sources": sources,
                    "timestamp": timestamp
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
    
    def update_feedback(self, query: str, feedback_score: float, answer: str = "", sources: List[Dict] = []):
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
                # 부정 피드백 시 자동 이메일 전송
                self.save_bad_feedback(query, answer, sources)
                
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
    """대화 맥락 구성"""
    if not context_history:
        return ""
    
    context_str = "이전 대화:\n"
    for idx, ctx in enumerate(context_history[-3:], 1):
        context_str += f"\n[{idx}]\n"
        context_str += f"Q: {ctx['query']}\n"
        context_str += f"A: {ctx['answer'][:150]}...\n"
    
    context_str += "\n위 대화를 참고하여 답변하세요.\n"
    return context_str


def process_query(query: str, rag_chain: RAGChainWrapper, learning_system: LearningSystem, 
                 logging_system: LoggingSystem, context: List[Dict] = None) -> Tuple[str, List[Dict], bool]:
    """쿼리 처리"""
    
    # 로깅만 수행
    query_id = logging_system.log_query(query, metadata={"context_length": len(context or [])})
    
    cache_key = hashlib.md5(query.encode()).hexdigest()
    
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
        
        if not filtered_docs or len(filtered_docs) < 2:
            use_web_search = True
        else:
            context_text = "\n\n".join([
                f"[문서 {i+1}] {doc.page_content}" 
                for i, (doc, _) in enumerate(filtered_docs)
            ])
            
            sources = [{
                'name': os.path.basename(doc.metadata.get("source", "")) if doc.metadata.get("source") else "검색 결과",
                'internal_score': float(score),
                'page': doc.metadata.get('page', 'N/A')
            } for doc, score in filtered_docs]
            
            if len(context_text) > 4000:
                context_text = context_text[:4000] + "\n..."
            
            if is_table_request:
                context_text += "\n\n⚠️ Markdown 표로 작성하세요."
                has_table = True
            
            # 프롬프트 생성
            formatted_prompt = rag_chain.prompt_template.format(
                context=context_text, 
                input=query,    
                history_context=history_context,
                conversation_context=conversation_context
            )
            
            answer = rag_chain.llm._call(formatted_prompt)
            
            if "|" in answer and "---" in answer:
                has_table = True
            
            if any(kw in answer for kw in ["찾을 수 없습니다", "정보가 없습니다"]) or len(answer.strip()) < 50:
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
    
    # 쿼리 처리
    answer, sources, has_table = process_query(query, RAG_CHAIN, LEARNING_SYSTEM, LOGGING_SYSTEM, context)
    
    # 답변에서 유사도 점수 제거
    clean_answer = re.sub(r'\s?\d\.\d{3}\b', '', answer).strip()

    # 출처 정보 구성 (중복 제거 및 원문 포함)
    unique_sources_data = []
    if sources:
        seen = set()
        for s in sources:
            # 1. 딕셔너리 혹은 Document 객체 여부 확인 후 데이터 추출
            if isinstance(s, dict):
                meta = s.get('metadata', {})
                # page_content가 없으면 content 키 확인
                text = s.get('page_content', s.get('content', ""))
            else:
                meta = getattr(s, 'metadata', {})
                text = getattr(s, 'page_content', "")

            # 2. 파일명 추출
            f_name = meta.get('file_name', meta.get('name', '참고 문서'))
            # 파일명 뒤의 숫자 제거 (정규식)
            f_name = re.sub(r'\s?\d\.\d{3}\b', '', str(f_name)).strip()

            # 3. 데이터가 있고 중복이 아닐 때만 리스트에 추가
            if f_name and text and f_name not in seen:
                unique_sources_data.append({
                    "name": f_name,   # app.py에서 source['name']으로 읽음
                    "content": text   # app.py에서 source['content']로 읽음
                })
                seen.add(f_name)

            return {
                "answer": clean_answer,
                "sources": unique_sources_data[:3], # 최대 3개 전송
                "has_table": has_table,
                "cached": False
            }


def submit_feedback(query: str, feedback_score: float, answer: str = "", sources: List[Dict] = []):
    """
    피드백 제출 (부정 피드백 시 자동 이메일 발송)
    """
    global LEARNING_SYSTEM
    if LEARNING_SYSTEM:
        LEARNING_SYSTEM.update_feedback(query, feedback_score, answer, sources)
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
    
def get_db_transport_advice(total_pallets: float):
    """
    Qdrant DB의 Unnamed 컬럼 데이터를 해석하여 최적의 차량을 제안합니다.
    """
    try:
        client = QdrantClient(url=QDRANT_HOST)
        
        # 1. 차량 데이터 시트의 내용 검색
        # 필터 조건은 실제 DB에 들어간 metadata나 page_content 내용에 맞춰 조정이 필요할 수 있습니다.
        search_result = client.scroll(
            collection_name="logistics_data",
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.sheet_name", 
                        match=models.MatchValue(value="차량 데이터")
                    )
                ]
            ),
            limit=100
        )[0]

        if not search_result:
            return None

        candidates = []
        for point in search_result:
            p = point.payload
            # metadata가 아닌 page_content(문자열)에 데이터가 있는 경우 파싱
            content = p.get("page_content", "")
            
            # 정규표현식이나 문자열 분할로 데이터 추출
            # 예: "Unnamed: 1: 트레일러 | Unnamed: 3: 12.0m | Unnamed: 4: 2.34m"
            try:
                name = re.search(r"Unnamed: 1:\s*([^|]+)", content).group(1).strip()
                length_str = re.search(r"Unnamed: 3:\s*([\d.]+)", content).group(1)
                width_str = re.search(r"Unnamed: 4:\s*([\d.]+)", content).group(1)
                
                length = float(length_str)
                width = float(width_str)
                
                # T11 팔레트(1.1m) 적재 계산
                cols = 2 if width >= 2.2 else 1 # 폭 2.2m 이상이면 2줄
                rows = length // 1.1
                max_plt = int(cols * rows)
                
                if max_plt >= total_pallets:
                    candidates.append({
                        "name": name,
                        "spec": f"길이 {length}m / 폭 {width}m",
                        "max_plt": max_plt
                    })
            except:
                continue

        # 가장 효율적인 차량(최대적재량이 물량에 가장 가까운 차량) 선택
        if candidates:
            best = sorted(candidates, key=lambda x: x['max_plt'])[0]
            return best
            
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