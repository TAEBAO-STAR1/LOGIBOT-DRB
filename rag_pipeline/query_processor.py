import os
import time
import json
import logging
import requests     
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv
from pydantic import PrivateAttr
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.llms import LLM
from langchain_qdrant import Qdrant
from langchain_ollama import OllamaEmbeddings 
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from ddgs import DDGS
from langchain_core.output_parsers import StrOutputParser

load_dotenv()
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# 환경 변수
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "logistics_data")
QDRANT_HOST = os.environ.get("QDRANT_HOST", "http://localhost:6333")
LEARNING_COLLECTION = os.environ.get("LEARNING_COLLECTION", "learning_history")
BAD_FEEDBACK_COLLECTION = os.environ.get("BAD_FEEDBACK_COLLECTION", "bad_feedback_history")
ONPREMISE_API_URL = os.getenv("ONPREMISE_API_URL", "http://192.168.1.120:11435/v1/chat/completions")
ONPREMISE_MODEL = os.getenv("ONPREMISE_MODEL", "ISTA-DASLab/gemma-3-27b-it-GPTQ-4b-128g")
ONPREMISE_TIMEOUT = int(os.getenv("ONPREMISE_TIMEOUT", "60"))
OLLAMA_EMBEDDING_MODEL = os.environ.get("OLLAMA_EMBEDDING_MODEL", "granite-embedding:278m")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# RAG 프롬프트 템플릿
PROMPT_TEMPLATE = """
당신은 물류 부서의 전문 AI 챗봇입니다.
다음 검색된 문맥(context)을 사용하여 사용자의 질문에 정확하고 친절하게 답변해 주세요.
{history_context}
답변 작성 규칙:
1. 핵심 내용을 먼저 간단히 요약하세요
2. 그 다음 줄에 "---" (구분선)을 넣으세요
3. 세부 사항은 번호나 bullet point로 구조화하세요
4. 절차나 프로세스는 단계별로 명확히 구분하세요
5. 답변은 명확하고 실무에 바로 적용 가능하도록 작성하세요
6. 반드시 제공된 문맥 내용을 기반으로만 답변하세요

<context>
{context}
</context>

질문: {input}

답변 (구조화된 형식으로, 특수문자 없이):
"""

class OnPremiseGemmaLLM(LLM):
    """온프레미스 Gemma 3 27B API용 LangChain LLM wrapper"""
    api_url: str = ONPREMISE_API_URL
    model: str = ONPREMISE_MODEL
    timeout: int = ONPREMISE_TIMEOUT
    max_retries: int = 3
    temperature: float = 0.2
    _last_call_ts: float = PrivateAttr(default=0.0)
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"api_url": self.api_url, "model": self.model}
    
    @property
    def _llm_type(self) -> str:
        return "onpremise_gemma"
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """온프레미스 API 호출"""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "stream": False
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
                else:
                    logger.warning(f"API 오류 (시도 {attempt}/{self.max_retries}): {response.status_code}")
                    if attempt < self.max_retries:
                        time.sleep(2 * attempt)
                    else:
                        raise RuntimeError(f"OnPremise API failed: {response.text}")
            
            except requests.Timeout:
                logger.warning(f"API 타임아웃 (시도 {attempt}/{self.max_retries})")
                if attempt < self.max_retries:
                    time.sleep(2 * attempt)
                else:
                    raise RuntimeError(f"OnPremise API timeout after {self.max_retries} retries")
            
            except Exception as e:
                logger.error(f"API 호출 오류 (시도 {attempt}/{self.max_retries}): {e}")
                if attempt < self.max_retries:
                    time.sleep(2 * attempt)
                else:
                    raise


class RAGChainWrapper:
    """RAG 체인 래퍼"""
    def __init__(self, vectorstore, llm, embeddings, qdrant_client):
        self.vectorstore = vectorstore
        self.llm = llm
        self.embeddings = embeddings
        self.qdrant_client = qdrant_client
        self.prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
        self.output_parser = StrOutputParser()


class LearningSystem:
    """누적 학습 시스템 - Good/Bad 피드백 분리 저장"""
    def __init__(self, qdrant_client: QdrantClient, embeddings: OllamaEmbeddings):
        self.client = qdrant_client
        self.embeddings = embeddings
        self.good_collection = LEARNING_COLLECTION
        self.bad_collection = BAD_FEEDBACK_COLLECTION  # Bad 피드백 전용 컬렉션
        self._ensure_collections()
    
    def _ensure_collections(self):
        """Good/Bad 피드백 저장용 컬렉션 생성"""
        try:
            collections = self.client.get_collections().collections
            existing_names = [c.name for c in collections]
            
            sample_vector = self.embeddings.embed_query("test")
            vector_size = len(sample_vector)
            
            # Good 피드백 컬렉션
            if self.good_collection not in existing_names:
                self.client.create_collection(
                    collection_name=self.good_collection,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                )
                logger.info(f"✅ Good 피드백 컬렉션 '{self.good_collection}' 생성 완료")
            
            # Bad 피드백 컬렉션
            if self.bad_collection not in existing_names:
                self.client.create_collection(
                    collection_name=self.bad_collection,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                )
                logger.info(f"✅ Bad 피드백 컬렉션 '{self.bad_collection}' 생성 완료")
                
        except Exception as e:
            logger.error(f"❌ 컬렉션 생성 오류: {e}")
    
    def save_interaction(self, query: str, answer: str, sources: List[Dict], 
                        feedback_score: Optional[float] = None):
        """질문-답변 조합을 Vector DB에 저장 (Good 피드백만)"""
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
                "usage_count": 1
            }
            
            self.client.upsert(
                collection_name=self.good_collection,
                points=[PointStruct(id=interaction_id, vector=query_vector, payload=metadata)]
            )
            logger.info(f"💾 Good 피드백 저장: {query[:50]}...")
            
        except Exception as e:
            logger.error(f"❌ Good 피드백 저장 실패: {e}")
    
    def save_bad_feedback(self, query: str, answer: str, sources: List[Dict]):
        """Bad 피드백을 별도 컬렉션에 저장"""
        try:
            query_vector = self.embeddings.embed_query(query)
            
            feedback_id = hashlib.md5(
                f"{query}_{datetime.now().isoformat()}_bad".encode()
            ).hexdigest()
            
            metadata = {
                "query": query,
                "answer": answer,
                "sources": json.dumps(sources, ensure_ascii=False),
                "timestamp": datetime.now().isoformat(),
                "feedback_type": "bad",
                "review_status": "pending"  # 나중에 리뷰를 위한 상태 플래그
            }
            
            self.client.upsert(
                collection_name=self.bad_collection,
                points=[PointStruct(id=feedback_id, vector=query_vector, payload=metadata)]
            )
            logger.info(f"⚠️ Bad 피드백 저장: {query[:50]}...")
            
        except Exception as e:
            logger.error(f"❌ Bad 피드백 저장 실패: {e}")
    
    def search_similar_interactions(self, query: str, limit: int = 3, 
                                   min_score: float = 0.7) -> List[Dict]:
        """유사한 과거 질문-답변 검색 (Good 피드백만)"""
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
                    'usage_count': result.payload.get('usage_count', 1),
                    'timestamp': result.payload.get('timestamp')
                })
                
                # 재사용 횟수 증가
                self.client.set_payload(
                    collection_name=self.good_collection,
                    payload={'usage_count': result.payload.get('usage_count', 1) + 1},
                    points=[result.id]
                )
            
            if interactions:
                logger.info(f"🔍 유사 질문 발견: {len(interactions)}개")
            
            return interactions
            
        except Exception as e:
            logger.error(f"❌ 과거 데이터 검색 실패: {e}")
            return []
    
    def update_feedback(self, query: str, feedback_score: float, answer: str = "", sources: List[Dict] = []):
        """사용자 피드백 기반 학습 데이터 품질 업데이트"""
        try:
            query_vector = self.embeddings.embed_query(query)
            
            # Good 피드백 (1.0)
            if feedback_score >= 0.5:
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
                    logger.info(f"📊 Good 피드백 반영: {new_score:.2f}")
            
            # Bad 피드백 (0.0)
            else:
                self.save_bad_feedback(query, answer, sources)
                logger.info(f"⚠️ Bad 피드백 별도 저장 완료")
                
        except Exception as e:
            logger.error(f"❌ 피드백 업데이트 실패: {e}")
    
    def get_bad_feedback_stats(self) -> Dict[str, Any]:
        """Bad 피드백 통계 조회"""
        try:
            result = self.client.count(collection_name=self.bad_collection)
            count = result.count if hasattr(result, 'count') else 0
            
            return {
                "total_bad_feedback": count,
                "collection_name": self.bad_collection
            }
        except Exception as e:
            logger.error(f"❌ Bad 피드백 통계 조회 실패: {e}")
            return {"total_bad_feedback": 0, "error": str(e)}


def setup_rag_chain():
    """RAG chain 구성"""
    logger.info("🚀 Setting up RAG chain...")
    
    llm = OnPremiseGemmaLLM()
    logger.info(f"✅ OnPremise Gemma 초기화 완료")
    
    embeddings = OllamaEmbeddings(model=OLLAMA_EMBEDDING_MODEL, base_url=OLLAMA_HOST)
    logger.info(f"✅ Ollama Embeddings 초기화 완료")
    
    qdrant_client = QdrantClient(url=QDRANT_HOST)
    vectorstore = Qdrant(client=qdrant_client, collection_name=QDRANT_COLLECTION, embeddings=embeddings)
    logger.info("✅ Qdrant 벡터스토어 연결 완료")
    
    rag_chain = RAGChainWrapper(vectorstore, llm, embeddings, qdrant_client)
    logger.info("✅ RAG chain setup complete!")
    return rag_chain


def search_ddg(query: str) -> str:
    """DuckDuckGo 웹 검색"""
    try:
        logger.info(f"🌐 DuckDuckGo 웹 검색 시작: {query}")
        results = DDGS().text(query, max_results=3)
        
        if not results:
            return ""
        
        context = [f"[출처 {i}] {r['title']}\n{r['body']}\nURL: {r['href']}\n" 
                   for i, r in enumerate(results, 1)]
        
        logger.info(f"✅ 웹 검색 완료: {len(results)}개 결과")
        return "\n".join(context)
        
    except Exception as e:
        logger.error(f"❌ 웹 검색 오류: {e}")
        return ""


def process_query(query: str, rag_chain: RAGChainWrapper, learning_system: LearningSystem) -> Tuple[str, List[Dict]]:
    """쿼리 처리 - 학습 시스템 통합"""
    logger.info(f"📝 Processing query: {query}")
    
    similar_interactions = learning_system.search_similar_interactions(query, limit=2, min_score=0.8)
    
    history_context = ""
    if similar_interactions:
        logger.info("🎓 과거 학습 데이터 활용")
        history_context = "참고: 과거 유사한 질문에 대한 답변\n"
        for idx, interaction in enumerate(similar_interactions, 1):
            history_context += f"\n[과거 질문 {idx}] {interaction['query']}\n"
            history_context += f"[답변] {interaction['answer'][:200]}...\n"
    
    answer = ""
    sources = []
    use_web_search = False
    
    try:
        logger.info("📚 Qdrant 로컬 DB 검색 중...")
        docs_with_scores = rag_chain.vectorstore.similarity_search_with_score(query, k=5)
        filtered_docs = [(doc, score) for doc, score in docs_with_scores if score >= 0.4]
        
        logger.info(f"검색된 문서: {len(docs_with_scores)}개, 필터링 후: {len(filtered_docs)}개")
        
        if not filtered_docs:
            use_web_search = True
        else:
            context = "\n\n".join([doc.page_content for doc, _ in filtered_docs])
            
            sources = [{
                'name': os.path.basename(doc.metadata.get("source", "")),
                'score': float(score),
                'page': doc.metadata.get('page', 'N/A')
            } for doc, score in filtered_docs if doc.metadata.get("source")]
            
            formatted_prompt = rag_chain.prompt_template.format(
                context=context, 
                input=query,
                history_context=history_context
            )
            
            answer = rag_chain.llm._call(formatted_prompt)
            
            insufficient_keywords = ["관련 정보를 찾을 수 없습니다", "찾을 수 없습니다", "정보가 없습니다"]
            
            if any(keyword in answer for keyword in insufficient_keywords):
                use_web_search = True
            else:
                logger.info("✅ Qdrant에서 충분한 답변 생성")
            
    except Exception as e:
        logger.exception(f"❌ Qdrant 검색 실패: {e}")
        use_web_search = True
    
    if use_web_search:
        logger.info("⚠️ 웹 검색으로 전환")
        web_context = search_ddg(query)
        sources = []
        
        if web_context:
            enhanced_prompt = f"""
다음은 웹에서 검색한 최신 정보입니다:

{web_context}

{history_context}

위 정보를 바탕으로 다음 질문에 답변해주세요.

질문: {query}

답변:
"""
            try:
                answer = rag_chain.llm._call(enhanced_prompt)
                answer += "\n\n🌐 웹 검색 결과 기반 답변"
                logger.info("✅ 웹 검색 기반 답변 생성 완료")
            except Exception as e:
                logger.error(f"❌ 답변 생성 실패: {e}")
                answer = "죄송하지만 답변을 생성할 수 없습니다."
        else:
            answer = "죄송하지만 관련 정보를 찾을 수 없습니다."
    
    learning_system.save_interaction(query, answer, sources)
    answer = format_answer(answer)
    
    return answer, sources


def format_answer(answer: str) -> str:
    """답변 구조화"""
    answer = answer.replace("**", "").replace("###", "").replace("##", "").replace("#", "")
    
    if any(marker in answer for marker in ["1.", "2.", "•", "-"]):
        return answer.strip()
    
    lines = [line.strip() for line in answer.strip().split('\n') if line.strip()]
    
    if len(lines) == 1:
        return answer.strip()
    
    formatted = f"핵심 요약:\n{lines[0]}\n\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if len(lines) > 1:
        formatted += "세부 내용:\n"
        for i, line in enumerate(lines[1:], 1):
            if line.strip():
                formatted += f"{i}. {line.strip()}\n"
    
    return formatted.strip()


# 모듈 로드 시 초기화
try:
    RAG_CHAIN = setup_rag_chain()
    LEARNING_SYSTEM = LearningSystem(RAG_CHAIN.qdrant_client, RAG_CHAIN.embeddings)
except Exception as e:
    logger.exception("❌ RAG CHAIN 초기화 실패")
    RAG_CHAIN = None
    LEARNING_SYSTEM = None


def get_rag_response(query: str) -> Dict[str, Any]:
    """RAG 응답 생성 (메인 API)"""
    global RAG_CHAIN, LEARNING_SYSTEM
    if RAG_CHAIN is None:
        logger.info("RAG_CHAIN 초기화 중...")
        RAG_CHAIN = setup_rag_chain()
        LEARNING_SYSTEM = LearningSystem(RAG_CHAIN.qdrant_client, RAG_CHAIN.embeddings)
    
    answer, sources = process_query(query, RAG_CHAIN, LEARNING_SYSTEM)
    
    source_info = ""
    if sources:
        sorted_sources = sorted(sources, key=lambda x: x['score'], reverse=True)
        source_list = [f"  • {s['name']} (유사도: {s['score']:.2f})" for s in sorted_sources[:3]]
        source_info = f"\n\n📚 참고 문서:\n" + "\n".join(source_list)
    
    return {'answer': answer + source_info, 'sources': sources}


def submit_feedback(query: str, feedback_score: float, answer: str = "", sources: List[Dict] = []):
    """사용자 피드백 제출 (Good/Bad 분리)"""
    global LEARNING_SYSTEM
    if LEARNING_SYSTEM:
        LEARNING_SYSTEM.update_feedback(query, feedback_score, answer, sources)
        feedback_type = "Good 👍" if feedback_score >= 0.5 else "Bad 👎"
        logger.info(f"✅ {feedback_type} 피드백 제출 완료: {query[:30]}...")
    else:
        logger.error("❌ LEARNING_SYSTEM이 초기화되지 않았습니다.")


def get_bad_feedback_report() -> Dict[str, Any]:
    """Bad 피드백 리포트 조회 (관리자용)"""
    global LEARNING_SYSTEM
    if LEARNING_SYSTEM:
        return LEARNING_SYSTEM.get_bad_feedback_stats()
    return {"error": "LEARNING_SYSTEM not initialized"}


if __name__ == "__main__":
    test_q = "컨베이어 벨트 유지보수 절차는?"
    try:
        result = get_rag_response(test_q)
        print("=" * 60)
        print(result['answer'])
        print("=" * 60)
        
        # Good 피드백 테스트
        submit_feedback(test_q, 1.0, result['answer'], result['sources'])
        # Bad 피드백 테스트
        submit_feedback(test_q, 0.0, result['answer'], result['sources'])        
        # Bad 피드백 통계
        stats = get_bad_feedback_report()
        print(f"\n📊 Bad 피드백 통계: {stats}")
        
    except Exception as e:
        logger.exception(f"Test failed: {e}")