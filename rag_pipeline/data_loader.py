import os
import sys
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Qdrant
from langchain_core.documents import Document
import pandas as pd


# 환경 변수 로드
load_dotenv()

# 환경 변수 정의 및 필수 변수 검증
MANDATORY_ENV_VARS = [
    "COLLECTION_NAME", "QDRANT_HOST", "QDRANT_PORT",
    "OLLAMA_EMBEDDING_MODEL", "OLLAMA_HOST"
]

# 환경 변수 검증 함수
def validate_env_vars():
    missing_vars = [var for var in MANDATORY_ENV_VARS if not os.getenv(var)]
    if missing_vars:
        print(f"Error: The following environment variables are missing in .env: {', '.join(missing_vars)}")
        sys.exit(1)

# 검증 실행
validate_env_vars()

# 환경 변수 로드
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
QDRANT_HOST = os.getenv("QDRANT_HOST")
# QDRANT_PORT는 문자열로 로드되므로 정수 변환을 시도합니다.
try:
    QDRANT_PORT = int(os.getenv("QDRANT_PORT"))
except (TypeError, ValueError):
    print("Error: QDRANT_PORT must be a valid integer.")
    sys.exit(1)

OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL") 
OLLAMA_HOST = os.getenv("OLLAMA_HOST")


def load_excel_documents(file_path: str) -> list[Document]:
    """
    Excel 파일을 로드하여 Document 객체 리스트로 변환합니다.
    각 시트를 별도의 문서로 처리하며, 행 단위로 텍스트를 생성합니다.
    
    Args:
        file_path: Excel 파일 경로
    
    Returns:
        Document 객체 리스트
    """
    documents = []
    file_name = os.path.basename(file_path)
    
    try:
        # Excel 파일의 모든 시트 읽기
        excel_file = pd.ExcelFile(file_path)
        
        for sheet_name in excel_file.sheet_names:
            print(f"  Processing sheet: {sheet_name}")
            
            # 시트를 DataFrame으로 읽기
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            # 빈 DataFrame 체크
            if df.empty:
                print(f"  Warning: Sheet '{sheet_name}' is empty, skipping.")
                continue
            
            # NaN 값을 빈 문자열로 대체
            df = df.fillna('')
            
            # 전체 시트를 하나의 텍스트로 변환 (테이블 형식 유지)
            sheet_text_parts = []
            
            # 컬럼 헤더 추가
            headers = " | ".join(str(col) for col in df.columns)
            sheet_text_parts.append(f"Sheet: {sheet_name}\n")
            sheet_text_parts.append(f"Columns: {headers}\n")
            sheet_text_parts.append("-" * 80 + "\n")
            
            # 각 행을 텍스트로 변환
            for idx, row in df.iterrows():
                row_text = " | ".join(
                    f"{col}: {str(val).strip()}" 
                    for col, val in zip(df.columns, row) 
                    if str(val).strip()
                )
                if row_text:  # 빈 행 제외
                    sheet_text_parts.append(f"Row {idx + 1}: {row_text}\n")
            
            sheet_content = "".join(sheet_text_parts)
            
            # 최소 콘텐츠 길이 체크
            if len(sheet_content.strip()) > 50:  # 최소 50자 이상만 처리
                doc = Document(
                    page_content=sheet_content,
                    metadata={
                        "source": file_path,
                        "file_name": file_name,
                        "sheet_name": sheet_name,
                        "row_count": len(df),
                        "column_count": len(df.columns),
                        "file_type": "excel"
                    }
                )
                documents.append(doc)
                print(f"  Success: Created document from sheet '{sheet_name}' ({len(df)} rows, {len(df.columns)} columns)")
            else:
                print(f"  Warning: Sheet '{sheet_name}' has insufficient content, skipping.")
        
        print(f"Success: Loaded {len(documents)} documents from {file_name}")
        
    except Exception as e:
        print(f"Error loading Excel file {file_name}: {e}")
    
    return documents


def load_and_split_documents(data_path: str = "data/source_docs") -> list[Document]:
    """
    지정된 경로의 PDF 및 Excel 문서를 로드하고 청크로 분할합니다.
    Args:
        data_path: 문서가 포함된 디렉토리 경로.
    Returns:
        분할된 Document 객체 리스트.
    """
    print(f"\n{'='*80}")
    print(f"Loading documents from {data_path}...")
    print(f"{'='*80}\n")
    documents = []
    
    # 1. PDF 문서 로드
    print("Loading PDF documents...")
    try:
        pdf_loader = PyPDFDirectoryLoader(data_path)
        pdf_docs = pdf_loader.load()
        documents.extend(pdf_docs)
        print(f"Success: Loaded {len(pdf_docs)} PDF documents.\n")
    except Exception as e:
        print(f"Error during PDF document loading: {e}\n")

    # 2. Excel 문서 (.xlsx, .xls) 로드
    print("Loading Excel documents...")
    
    # 디버깅: 디렉토리 내 모든 파일 출력
    try:
        all_files = os.listdir(data_path)
        print(f"Files in directory '{data_path}':")
        for f in all_files:
            file_path = os.path.join(data_path, f)
            if os.path.isfile(file_path):
                file_size = os.path.getsize(file_path)
                print(f"  - {f} ({file_size} bytes)")
            else:
                print(f"  - {f} (directory)")
        print()
    except Exception as e:
        print(f"Error listing directory: {e}\n")
    
    # Excel 파일 필터링 (대소문자 무시, 임시 파일 제외)
    excel_files = []
    for f in os.listdir(data_path):
        if f.lower().endswith(('.xlsx', '.xls')) and not f.startswith('~$'):
            excel_files.append(f)
    
    if excel_files:
        print(f"Found {len(excel_files)} Excel file(s):\n")
        excel_doc_count = 0
        for file_name in excel_files:
            print(f"Processing: {file_name}")
            file_path = os.path.join(data_path, file_name)
            excel_docs = load_excel_documents(file_path)
            documents.extend(excel_docs)
            excel_doc_count += len(excel_docs)
            print()
        
        print(f"Success: Total Excel documents loaded: {excel_doc_count}\n")
    else:
        print("No Excel files found.\n")

    if not documents:
        print("Warning: No PDF or Excel documents were found to process.")
        return []

    print(f"{'='*80}")
    print(f"Total documents loaded: {len(documents)}")
    print(f"{'='*80}\n")

    # 문서 내용 검증
    print("Validating document contents...")
    valid_documents = []
    for i, doc in enumerate(documents):
        if doc.page_content and len(doc.page_content.strip()) > 20:
            valid_documents.append(doc)
        else:
            print(f"Warning: Skipping document {i+1}: insufficient content")
    
    print(f"Valid documents after filtering: {len(valid_documents)}\n")

    # 재귀적 문자 분할기를 사용하여 문서를 청크로 나눕니다.
    print("Splitting documents into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.split_documents(valid_documents)
    
    print(f"Success: Total chunks created: {len(chunks)}\n")
    
    # 청크 샘플 출력 (디버깅용)
    if chunks:
        print("Sample chunk preview:")
        print("-" * 80)
        print(f"Content: {chunks[0].page_content[:200]}...")
        print(f"Metadata: {chunks[0].metadata}")
        print("-" * 80 + "\n")
    
    return chunks


def index_documents_to_qdrant(chunks: list[Document]):
    """
    분할된 청크를 임베딩하여 Qdrant 벡터 저장소에 적재합니다.
    """
    if not chunks:
        print("No chunks to index. Exiting indexing process.")
        return

    qdrant_url = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
    print(f"{'='*80}")
    print(f"Initializing Qdrant client at {qdrant_url}")
    print(f"{'='*80}\n")
    
    # Qdrant 클라이언트 초기화
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    
    # Ollama 임베딩 모델 초기화 (Ollama 서버에서 임베딩 수행)
    print(f"Initializing embedding model: {OLLAMA_EMBEDDING_MODEL}")
    embeddings = OllamaEmbeddings(model=OLLAMA_EMBEDDING_MODEL, base_url=OLLAMA_HOST)

    # 임베딩 차원 동적 확인
    print("Detecting embedding vector dimensions...")
    try:
        sample_vector = embeddings.embed_query("This is a test query to get the dimension.")
        vector_size = len(sample_vector)
        print(f"Success: Detected vector size for '{OLLAMA_EMBEDDING_MODEL}': {vector_size}\n")
    except Exception as e:
        print(f"Error getting embedding dimension from Ollama. Check Ollama server and model name. Error: {e}")
        vector_size = 768
        print(f"Using default vector size: {vector_size}\n")

    # Qdrant 컬렉션 존재 여부 확인 및 생성/재생성
    print(f"Setting up collection: {COLLECTION_NAME}")
    collections = client.get_collections().collections
    if COLLECTION_NAME in [c.name for c in collections]:
        print(f"Collection '{COLLECTION_NAME}' already exists. Recreating it for a fresh index...")
        client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE
            )
        )
    else:
        print(f"Creating new collection: '{COLLECTION_NAME}'...")
        client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE
            )
        )
    print("Success: Collection ready\n")

    # 청크를 Qdrant에 저장
    print(f"{'='*80}")
    print(f"Indexing {len(chunks)} chunks into Qdrant...")
    print(f"{'='*80}\n")
    
    try:
        # 파일 타입별 통계
        file_types = {}
        for chunk in chunks:
            ftype = chunk.metadata.get('file_type', 'pdf')
            file_types[ftype] = file_types.get(ftype, 0) + 1
        
        print("Chunks by file type:")
        for ftype, count in file_types.items():
            print(f"  - {ftype.upper()}: {count} chunks")
        print()
        
        Qdrant.from_documents(
            chunks,
            embeddings,
            collection_name=COLLECTION_NAME,
            url=qdrant_url,
            force_recreate=False
        )
        print(f"\n{'='*80}")
        print("Success: Document indexing complete!")
        print(f"{'='*80}\n")
    except Exception as e:
        print(f"Error during Qdrant indexing: {e}")


if __name__ == "__main__":
    DATA_FOLDER = "data/source_docs"
    
    # 데이터 폴더가 없으면 생성
    if not os.path.exists(DATA_FOLDER):
        os.makedirs(DATA_FOLDER, exist_ok=True)
        
    # PDF 또는 Excel 파일이 있는지 확인
    has_files = any(
        fname.lower().endswith(('.pdf', '.xlsx', '.xls')) 
        for fname in os.listdir(DATA_FOLDER)
    )
    
    if not has_files:
        print("=" * 80)
        print(f"INFO: Please place your PDF and/or Excel documents into the '{DATA_FOLDER}' folder.")
        print("Run the script again after adding your files.")
        print("=" * 80)
    else:
        # 문서 로드 및 벡터화 시작
        logistics_chunks = load_and_split_documents(data_path=DATA_FOLDER)
        if logistics_chunks:
            index_documents_to_qdrant(logistics_chunks)
        else:
            print("No valid chunks were created. Please check your source documents.")