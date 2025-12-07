import os
import sys
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from langchain_community.document_loaders import PyPDFDirectoryLoader, UnstructuredExcelLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Qdrant
from langchain_core.documents import Document


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

# 1. 문서 로드 및 청킹 설정
def load_and_split_documents(data_path: str = "data/source_docs") -> list[Document]:
    """
    지정된 경로의 PDF 및 Excel 문서를 로드하고 청크로 분할합니다.
    Args:
        data_path: 문서가 포함된 디렉토리 경로.
    Returns:
        분할된 Document 객체 리스트.
    """
    print(f"Loading documents from {data_path}...")
    documents = []
    
    # 1. PDF 문서 로드
    try:
        pdf_loader = PyPDFDirectoryLoader(data_path)
        documents.extend(pdf_loader.load())
        print(f"Loaded {len(documents)} initial PDF documents.")
    except Exception as e:
        print(f"Error during PDF document loading: {e}")

    # 2. Excel 문서 (.xlsx, .xls) 로드
    excel_files = [f for f in os.listdir(data_path) if f.endswith(('.xlsx', '.xls'))]
    if excel_files:
        print(f"Found {len(excel_files)} Excel files. Loading them...")
        for file_name in excel_files:
            file_path = os.path.join(data_path, file_name)
            try:
                # UnstructuredExcelLoader를 사용하여 Excel 파일을 로드합니다.
                # mode="elements"는 Excel 셀/테이블을 구조화된 요소로 추출하는 데 도움이 됩니다.
                excel_loader = UnstructuredExcelLoader(file_path, mode="elements")
                documents.extend(excel_loader.load())
                print(f"Successfully loaded {file_name}")
            except Exception as e:
                # Excel 파일 로드에 실패하면 경고 메시지를 출력하고 다음 파일로 넘어갑니다.
                print(f"Error loading Excel file {file_name}: Please ensure 'unstructured' and 'openpyxl' are installed. Error: {e}")

    if not documents:
        print("Warning: No PDF or Excel documents were found to process.")
        return []

    # 재귀적 문자 분할기를 사용하여 문서를 청크로 나눕니다.
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.split_documents(documents)
    
    print(f"Total documents loaded: {len(documents)}")
    print(f"Total chunks created: {len(chunks)}")
    return chunks

# 2. Qdrant 벡터 저장소 설정 및 데이터 적재
def index_documents_to_qdrant(chunks: list[Document]):
    """
    분할된 청크를 임베딩하여 Qdrant 벡터 저장소에 적재합니다.
    """
    if not chunks:
        print("No chunks to index. Exiting indexing process.")
        return

    qdrant_url = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
    print(f"Initializing Qdrant client at {qdrant_url}")
    
    # Qdrant 클라이언트 초기화
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    
    # Ollama 임베딩 모델 초기화 (Ollama 서버에서 임베딩 수행)
    embeddings = OllamaEmbeddings(model=OLLAMA_EMBEDDING_MODEL, base_url=OLLAMA_HOST)

    # --- 임베딩 차원 동적 확인 ---
    # Qdrant 컬렉션을 생성하기 위해 임베딩 모델의 차원(dimension)을 확인합니다.
    try:
        sample_vector = embeddings.embed_query("This is a test query to get the dimension.")
        vector_size = len(sample_vector)
        print(f"Detected vector size for '{OLLAMA_EMBEDDING_MODEL}': {vector_size}")
    except Exception as e:
        print(f"Error getting embedding dimension from Ollama. Check Ollama server and model name. Error: {e}")
        # 임시 기본값 (일반적인 크기) 사용 또는 종료
        vector_size = 768
        print(f"Using default vector size: {vector_size}")


    # --- Qdrant 컬렉션 존재 여부 확인 및 생성/재생성 ---
    collections = client.get_collections().collections
    if COLLECTION_NAME in [c.name for c in collections]:
        print(f"Collection {COLLECTION_NAME} already exists. Recreating it for a fresh index.")
        # 기존 컬렉션을 삭제하고 새로 생성
        client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE
            )
        )
    else:
        print(f"Creating new collection: {COLLECTION_NAME}")
        client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE
            )
        )

    # --- 청크를 Qdrant에 저장 ---
    print(f"Indexing {len(chunks)} chunks into Qdrant...")
    try:
        Qdrant.from_documents(
            chunks,
            embeddings,
            collection_name=COLLECTION_NAME,
            url=qdrant_url,
            force_recreate=False # 이미 클라이언트에서 처리했으므로 False
        )
        print("Document indexing complete!")
    except Exception as e:
        print(f"Error during Qdrant indexing: {e}")


if __name__ == "__main__":
    DATA_FOLDER = "data/source_docs"
    # 데이터 폴더가 없으면 생성하고 사용자에게 PDF 및 Excel 파일을 넣도록 안내합니다.
    if not os.path.exists(DATA_FOLDER):
        os.makedirs(DATA_FOLDER, exist_ok=True)
        
    # PDF 또는 Excel 파일이 있는지 확인
    has_files = any(fname.endswith(('.pdf', '.xlsx', '.xls')) for fname in os.listdir(DATA_FOLDER))
    
    if not has_files:
        print("-" * 50)
        print(f"⚠️ INFO: Please place your PDF and/or Excel documents into the '{DATA_FOLDER}' folder.")
        print("Run the script again after adding your files.")
        print("-" * 50)
    else:
        # 이 함수를 실행하여 DB 적재를 시작합니다.
        logistics_chunks = load_and_split_documents(data_path=DATA_FOLDER)
        if logistics_chunks:
            index_documents_to_qdrant(logistics_chunks)