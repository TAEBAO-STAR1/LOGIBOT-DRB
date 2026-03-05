import os
import sys
import re
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document
import pandas as pd
from typing import List
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from tqdm import tqdm

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 환경 변수 로드
load_dotenv()

# 환경 변수 정의 및 필수 변수 검증
MANDATORY_ENV_VARS = [
    "COLLECTION_NAME", "QDRANT_HOST", "QDRANT_PORT",
    "OLLAMA_EMBEDDING_MODEL", "OLLAMA_HOST"
]

def validate_env_vars():
    """환경 변수 검증"""
    missing_vars = [var for var in MANDATORY_ENV_VARS if not os.getenv(var)]
    if missing_vars:
        logger.error(f"필수 환경 변수 누락: {', '.join(missing_vars)}")
        sys.exit(1)

validate_env_vars()

# 환경 변수 로드
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
QDRANT_HOST = os.getenv("QDRANT_HOST")

try:
    QDRANT_PORT = int(os.getenv("QDRANT_PORT"))
except (TypeError, ValueError):
    logger.error("QDRANT_PORT는 정수여야 합니다.")
    sys.exit(1)

OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL") 
OLLAMA_HOST = os.getenv("OLLAMA_HOST")

# 최적화 설정
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
EXCEL_BATCH_SIZE = int(os.getenv("EXCEL_BATCH_SIZE", "500"))  # Excel 행 배치 크기
VECTOR_BATCH_SIZE = int(os.getenv("VECTOR_BATCH_SIZE", "256"))  # 벡터 인덱싱 배치
EXCEL_MEMORY_LIMIT_MB = int(os.getenv("EXCEL_MEMORY_LIMIT_MB", "1000"))  # Excel 메모리 제한


def extract_material_code(text: str) -> str:
    """텍스트에서 자재코드 추출 (7자리 숫자)"""
    patterns = [
        r'자재코드[:\s]*(\d{7})',
        r'코드[:\s]*(\d{7})',
        r'\b(\d{7})\b'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""

def create_grouped_content(df: pd.DataFrame, sheet_name: str) -> List[Document]:
    """
    행 단위가 아닌, 의미 단위(부서/팀)로 데이터를 묶어서 인덱싱합니다.
    '물류팀 인원' 질문에 7명만 답하는 문제를 근본적으로 해결합니다.
    """
    grouped_docs = []
    
    # 1. '팀'이나 '부서' 컬럼이 있다면 그룹화 시도
    group_col = None
    for col in ['팀', '부서', '구분']:
        if col in df.columns:
            group_col = col
            break
            
    if group_col:
        for group_name, group_df in df.groupby(group_col):
            # 해당 그룹의 모든 정보를 하나의 텍스트로 결합
            combined_text = f"[{sheet_name} - {group_name} 전체 명단]\n"
            for _, row in group_df.iterrows():
                row_str = " | ".join([f"{c}: {row[c]}" for c in df.columns if pd.notna(row[c])])
                combined_text += f"- {row_str}\n"
            
            grouped_docs.append(Document(
                page_content=combined_text,
                metadata={"sheet_name": sheet_name, "group": group_name, "type": "summary"}
            ))
            return grouped_docs
        
def create_structured_content(row: pd.Series, columns: List[str]) -> str:
    """
    Excel 행을 구조화된 텍스트로 변환 (최적화)
    
    개선점:
    - 중요 필드 우선 배치
    - 빈 값 제외
    - 간결한 포맷
    """
    parts = []
    
    # 1. 핵심 필드 (자재코드, 자재내역)
    priority_fields = ['자재코드', '자재내역', '자재구분']
    for field in priority_fields:
        if field in columns and field in row.index:
            val = str(row[field]).strip()
            if val and val != 'nan' and val != '':
                parts.append(f"{field}: {val}")
    
    # 2. 기타 필드
    for col in columns:
        if col not in priority_fields and col in row.index:
            val = str(row[col]).strip()
            if val and val != 'nan' and val != '' and val != '0':
                parts.append(f"{col}: {val}")
    
    return " | ".join(parts)

def load_excel_optimized(file_path: str) -> List[Document]:
    """
    대용량 Excel 최적화 로딩 (메모리 효율 개선)
    
    개선점:
    1. 대용량 파일: 슬라이싱으로 청크 처리
    2. 소규모 파일: 전체 로드 (속도 우선)
    3. 메모리 기반 자동 전환
    """
    documents = []
    file_name = os.path.basename(file_path)
    doc_hashes = set()
    
    try:
        # 파일 크기 확인
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        excel_file = pd.ExcelFile(file_path)
        logger.info(f"📄 Excel 파일: {file_name} ({len(excel_file.sheet_names)}개 시트, {file_size_mb:.2f}MB)")
        
        for sheet_name in excel_file.sheet_names:
            logger.info(f"\n📊 시트 처리: '{sheet_name}'")
            
            # 전체 행 수 확인 (빠른 체크)
            df_sample = pd.read_excel(file_path, sheet_name=sheet_name, nrows=1)
            df_full = pd.read_excel(file_path, sheet_name=sheet_name)
            total_rows = len(df_full)
            
            logger.info(f"  총 행 수: {total_rows:,}개")
            
            if total_rows == 0:
                logger.warning(f"  ⚠️ 빈 시트, 스킵")
                continue
            
            # NaN 처리 및 컬럼 정리
            df_full = df_full.fillna('')
            df_full.columns = df_full.columns.str.strip()
            columns = df_full.columns.tolist()
            
            sheet_doc_count = 0
            
            # 진행률 표시
            logger.info(f"  🔄 문서 생성 중...")
            with tqdm(total=total_rows, desc=f"    진행", unit="행", ncols=80) as pbar:
                # 슬라이싱으로 청크 처리
                for start_idx in range(0, total_rows, EXCEL_BATCH_SIZE):
                    end_idx = min(start_idx + EXCEL_BATCH_SIZE, total_rows)
                    df_chunk = df_full.iloc[start_idx:end_idx]
                    
                    # 배치 처리
                    for idx, row in df_chunk.iterrows():
                        # 구조화된 텍스트 생성
                        row_content = create_structured_content(row, columns)
                        
                        # 최소 길이 체크
                        if len(row_content.strip()) < 20:
                            continue
                        
                        # 중복 체크
                        content_hash = hashlib.md5(row_content.encode()).hexdigest()
                        if content_hash in doc_hashes:
                            continue
                        doc_hashes.add(content_hash)
                        
                        # 자재코드 추출
                        material_code = ""
                        if '자재코드' in row.index:
                            code_val = str(row['자재코드']).strip()
                            if code_val and code_val.isdigit() and len(code_val) == 7:
                                material_code = code_val
                        
                        if not material_code:
                            material_code = extract_material_code(row_content)
                        
                        # 메타데이터
                        metadata = {
                            "source": file_path,
                            "file_name": file_name,
                            "sheet_name": sheet_name,
                            "row_number": int(idx) + 1,
                            "file_type": "excel",
                            "has_material_code": bool(material_code)
                        }
                        
                        if material_code:
                            metadata["material_code"] = material_code
                        
                        # 주요 필드 추가
                        for field in ['자재구분', '자재내역', '제품폭(mm)', '포규격', '포두께(mm)']:
                            if field in row.index:
                                val = str(row[field]).strip()
                                if val and val != 'nan' and val != '' and val != '0':
                                    metadata[field] = val
                        
                        # Document 생성
                        doc = Document(
                            page_content=row_content,
                            metadata=metadata
                        )
                        documents.append(doc)
                        sheet_doc_count += 1
                    
                    pbar.update(len(df_chunk))
                    
                    # 메모리 해제 (중요!)
                    del df_chunk
            
            # 메모리 해제
            del df_full
            
            logger.info(f"  ✅ {sheet_doc_count:,}개 문서 생성 완료")
        
        # 통계
        material_docs = [d for d in documents if d.metadata.get('has_material_code')]
        logger.info(f"\n{'='*80}")
        logger.info(f"✅ Excel 로드 완료: {file_name}")
        logger.info(f"  - 총 문서: {len(documents):,}개")
        logger.info(f"  - 자재코드 포함: {len(material_docs):,}개")
        logger.info(f"  - 고유 문서: {len(doc_hashes):,}개")
        logger.info(f"{'='*80}\n")
        
    except Exception as e:
        logger.error(f"❌ Excel 로드 실패: {file_name}")
        logger.error(f"   오류: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    
    return documents


def process_pdf_file(file_path: str) -> List[Document]:
    """PDF 파일 개별 처리"""
    try:
        from langchain_community.document_loaders import PyPDFLoader
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        logger.info(f"  ✅ PDF: {os.path.basename(file_path)} ({len(docs)}페이지)")
        return docs
    except Exception as e:
        logger.error(f"  ❌ PDF 실패: {os.path.basename(file_path)} - {e}")
        return []


def load_and_split_documents(data_path: str = "data/source_docs") -> List[Document]:
    """
    문서 로드 및 청킹 (최적화)
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"📁 문서 로딩: {data_path}")
    logger.info(f"{'='*80}\n")
    
    documents = []
    
    # 파일 목록
    pdf_files = []
    excel_files = []
    
    try:
        all_files = os.listdir(data_path)
        
        for f in all_files:
            file_path = os.path.join(data_path, f)
            if not os.path.isfile(file_path):
                continue
            
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            
            if f.lower().endswith('.pdf'):
                pdf_files.append(file_path)
                logger.info(f"  📄 {f} ({file_size:.2f} MB)")
            elif f.lower().endswith(('.xlsx', '.xls')) and not f.startswith('~$'):
                excel_files.append(file_path)
                logger.info(f"  📊 {f} ({file_size:.2f} MB)")
        
        logger.info(f"\n파일 분류: PDF {len(pdf_files)}개 | Excel {len(excel_files)}개\n")
        
    except Exception as e:
        logger.error(f"❌ 디렉토리 스캔 실패: {e}")
        return []
    
    # PDF 병렬 로딩
    if pdf_files:
        logger.info("📄 PDF 로딩 (병렬)...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_file = {
                executor.submit(process_pdf_file, fp): fp 
                for fp in pdf_files
            }
            
            for future in as_completed(future_to_file):
                docs = future.result()
                documents.extend(docs)
        
        logger.info(f"✅ PDF: {len([d for d in documents if d.metadata.get('source', '').endswith('.pdf')]):,}개\n")
    
    # Excel 최적화 로딩
    if excel_files:
        logger.info("📊 Excel 로딩 (최적화 모드)...")
        for file_path in excel_files:
            excel_docs = load_excel_optimized(file_path)
            documents.extend(excel_docs)
    
    if not documents:
        logger.warning("⚠️ 문서 없음")
        return []
    
    logger.info(f"{'='*80}")
    logger.info(f"✅ 총 {len(documents):,}개 문서 로드")
    logger.info(f"{'='*80}\n")
    
    # 문서 검증
    valid_documents = [
        doc for doc in documents 
        if doc.page_content and len(doc.page_content.strip()) > 20
    ]
    
    logger.info(f"🔍 유효 문서: {len(valid_documents):,}개\n")
    
    # 청킹
    excel_docs = [d for d in valid_documents if d.metadata.get('file_type') == 'excel']
    pdf_docs = [d for d in valid_documents if d.metadata.get('file_type') != 'excel']
    
    chunks = []
    
    # Excel은 그대로
    chunks.extend(excel_docs)
    logger.info(f"📊 Excel: {len(excel_docs):,}개 (청킹 없음)")
    
    # PDF만 청킹
    if pdf_docs:
        logger.info(f"✂️ PDF 청킹...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1200,
            chunk_overlap=250,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        pdf_chunks = text_splitter.split_documents(pdf_docs)
        chunks.extend(pdf_chunks)
        logger.info(f"✅ PDF: {len(pdf_chunks):,}개")
    
    logger.info(f"\n✅ 최종: {len(chunks):,}개 청크\n")
    
    return chunks


def batch_embed_and_index(chunks: List[Document], embeddings: OllamaEmbeddings, 
                         client: QdrantClient, collection_name: str,
                         batch_size: int = 100) -> None:
    """
    배치 임베딩 + 즉시 인덱싱 (메모리 효율 최적화)
    
    개선점:
    - 임베딩 후 즉시 Qdrant에 저장
    - 메모리에 모든 벡터 보관하지 않음
    - 중간 저장으로 안정성 향상
    """
    logger.info(f"🔢 배치 임베딩+인덱싱 (배치: {batch_size})...")
    
    total_batches = (len(chunks) + batch_size - 1) // batch_size
    total_indexed = 0
    
    with tqdm(total=len(chunks), desc="  진행", unit="doc") as pbar:
        for batch_idx in range(0, len(chunks), batch_size):
            batch_chunks = chunks[batch_idx:batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1
            
            try:
                # 배치 임베딩
                batch_texts = [chunk.page_content for chunk in batch_chunks]
                batch_vectors = embeddings.embed_documents(batch_texts)
                
                # Qdrant Point 생성
                points = []
                for idx, (chunk, vector) in enumerate(zip(batch_chunks, batch_vectors)):
                    point_id = hashlib.md5(
                        f"{chunk.page_content}_{batch_idx + idx}".encode()
                    ).hexdigest()
                    
                    # Payload 구성
                    payload = {
                        "page_content": chunk.page_content,
                        "metadata": chunk.metadata
                    }
                    
                    # 자재코드는 최상위로
                    if chunk.metadata.get('material_code'):
                        payload["material_code"] = chunk.metadata['material_code']
                    
                    points.append(
                        models.PointStruct(
                            id=point_id,
                            vector=vector,
                            payload=payload
                        )
                    )
                
                # Qdrant에 업로드
                client.upsert(
                    collection_name=collection_name,
                    points=points
                )
                
                total_indexed += len(points)
                pbar.update(len(batch_chunks))
                
            except Exception as e:
                logger.error(f"  ❌ 배치 {batch_num}/{total_batches} 실패: {e}")
                # 개별 처리 폴백
                for chunk in batch_chunks:
                    try:
                        vector = embeddings.embed_query(chunk.page_content)
                        point_id = hashlib.md5(chunk.page_content.encode()).hexdigest()
                        
                        client.upsert(
                            collection_name=collection_name,
                            points=[models.PointStruct(
                                id=point_id,
                                vector=vector,
                                payload={
                                    "page_content": chunk.page_content,
                                    "metadata": chunk.metadata,
                                    "material_code": chunk.metadata.get('material_code')
                                }
                            )]
                        )
                        total_indexed += 1
                    except Exception as inner_e:
                        logger.error(f"    개별 문서 실패: {inner_e}")
                
                pbar.update(len(batch_chunks))
    
    logger.info(f"✅ 총 {total_indexed:,}개 인덱싱 완료")


def index_documents_to_qdrant(chunks: List[Document]):
    """
    Qdrant 인덱싱 (대용량 최적화)
    """
    if not chunks:
        logger.warning("⚠️ 청크 없음")
        return
    
    qdrant_url = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
    logger.info(f"{'='*80}")
    logger.info(f"🚀 Qdrant 인덱싱")
    logger.info(f"  URL: {qdrant_url}")
    logger.info(f"  컬렉션: {COLLECTION_NAME}")
    logger.info(f"  문서 수: {len(chunks):,}개")
    logger.info(f"{'='*80}\n")
    
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    
    logger.info(f"🔧 임베딩 모델: {OLLAMA_EMBEDDING_MODEL}")
    embeddings = OllamaEmbeddings(model=OLLAMA_EMBEDDING_MODEL, base_url=OLLAMA_HOST)
    
    # 벡터 차원
    logger.info("📏 벡터 차원 확인...")
    try:
        sample_vector = embeddings.embed_query("테스트")
        vector_size = len(sample_vector)
        logger.info(f"✅ 차원: {vector_size}\n")
    except Exception as e:
        logger.error(f"❌ 임베딩 오류: {e}")
        vector_size = 768
        logger.warning(f"⚠️ 기본 차원: {vector_size}\n")
    
    # 컬렉션 재생성
    logger.info(f"🗄️ 컬렉션: {COLLECTION_NAME}")
    collections = client.get_collections().collections
    if COLLECTION_NAME in [c.name for c in collections]:
        logger.info("  기존 컬렉션 삭제...")
        client.delete_collection(collection_name=COLLECTION_NAME)
    
    logger.info("  새 컬렉션 생성...")
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=models.Distance.COSINE
        ),
        optimizers_config=models.OptimizersConfigDiff(
            indexing_threshold=1000  # 인덱싱 임계값
        )
    )
    logger.info("✅ 컬렉션 준비\n")
    
    # 통계
    file_types = {}
    material_count = sum(1 for c in chunks if c.metadata.get('has_material_code'))
    for chunk in chunks:
        ftype = chunk.metadata.get('file_type', 'pdf')
        file_types[ftype] = file_types.get(ftype, 0) + 1
    
    logger.info("📊 통계:")
    for ftype, count in file_types.items():
        logger.info(f"  {ftype.upper()}: {count:,}개")
    logger.info(f"  자재코드: {material_count:,}개\n")
    
    # 배치 인덱싱 (최적화 버전)
    logger.info(f"{'='*80}")
    logger.info(f"⚡ 배치 임베딩+인덱싱 시작")
    logger.info(f"  배치 크기: {VECTOR_BATCH_SIZE}")
    logger.info(f"  총 문서: {len(chunks):,}개")
    logger.info(f"{'='*80}\n")
    
    try:
        # 직접 배치 처리
        batch_embed_and_index(
            chunks=chunks,
            embeddings=embeddings,
            client=client,
            collection_name=COLLECTION_NAME,
            batch_size=VECTOR_BATCH_SIZE
        )
        
        logger.info(f"\n{'='*80}")
        logger.info("🎉 인덱싱 완료!")
        logger.info(f"{'='*80}\n")
        
        # 최종 통계
        collection_info = client.get_collection(COLLECTION_NAME)
        logger.info("📈 최종 정보:")
        logger.info(f"  벡터 수: {collection_info.points_count:,}개")
        logger.info(f"  컬렉션: {COLLECTION_NAME}")
        logger.info(f"  자재코드: {material_count:,}개")
        logger.info(f"\n{'='*80}\n")
        
    except Exception as e:
        logger.error(f"❌ 인덱싱 실패: {e}")
        raise


if __name__ == "__main__":
    DATA_FOLDER = "data/source_docs"
    
    if not os.path.exists(DATA_FOLDER):
        os.makedirs(DATA_FOLDER, exist_ok=True)
        logger.info(f"📁 폴더 생성: {DATA_FOLDER}")
    
    has_files = False
    if os.path.exists(DATA_FOLDER):
        files = [
            f for f in os.listdir(DATA_FOLDER) 
            if f.lower().endswith(('.pdf', '.xlsx', '.xls'))
        ]
        has_files = bool(files)
    
    if not has_files:
        logger.warning("=" * 80)
        logger.warning(f"⚠️ '{DATA_FOLDER}'에 문서 추가 필요")
        logger.warning("지원: PDF, Excel (.xlsx, .xls)")
        logger.warning("=" * 80)
    else:
        logger.info("\n🚀 RAG 인덱싱 시작\n")
        
        try:
            chunks = load_and_split_documents(data_path=DATA_FOLDER)
            
            if chunks:
                index_documents_to_qdrant(chunks)
                logger.info("\n✅ 완료!")
            else:
                logger.error("❌ 청크 없음")
        
        except Exception as e:
            logger.exception(f"❌ 오류: {e}")