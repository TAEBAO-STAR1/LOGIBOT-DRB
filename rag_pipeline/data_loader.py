import os
import sys
import re
import hashlib
import logging
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
import pandas as pd
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

MANDATORY_ENV_VARS = ["COLLECTION_NAME", "QDRANT_HOST", "QDRANT_PORT",
                      "OLLAMA_EMBEDDING_MODEL", "OLLAMA_HOST"]

def validate_env_vars():
    missing = [v for v in MANDATORY_ENV_VARS if not os.getenv(v)]
    if missing:
        logger.error(f"필수 환경 변수 누락: {', '.join(missing)}")
        sys.exit(1)

validate_env_vars()

COLLECTION_NAME        = os.getenv("COLLECTION_NAME")
QDRANT_HOST            = os.getenv("QDRANT_HOST")
QDRANT_PORT            = int(os.getenv("QDRANT_PORT"))
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL")
OLLAMA_HOST            = os.getenv("OLLAMA_HOST")
MAX_WORKERS            = int(os.getenv("MAX_WORKERS", "4"))
VECTOR_BATCH_SIZE      = int(os.getenv("VECTOR_BATCH_SIZE", "128"))

# ── 시트별 청킹 전략 ──────────────────────────────────────────────────────────
# WHOLE : 시트 전체 → 1개 문서 (수식/규칙/소규모 테이블)
# QA    : 행(질문-답변) 단위로 각 1개 문서
# GROUP : 특정 컬럼 기준 그룹핑
# ROW   : 자재코드 기반 행 단위 문서
SHEET_STRATEGY: Dict[str, str] = {
    "수출 포장량 산출 수식"          : "WHOLE",
    "포장량 산출 데이터"             : "WHOLE",
    "차량 데이터"                    : "WHOLE",
    "컨베어벨트 직경 산출 수식"      : "WHOLE",
    "파렛트, 박스 데이터"            : "WHOLE",
    "물류팀 운영 규칙"               : "QA",
    "물류팀 현황 데이터"             : "GROUP",   # 담당자 정보 — GROUP 전략
    "컨베어벨트 규격 데이터"         : "ROW",
    "주름혹벨트 우든박스 사이즈 데이터": "ROW",
    "크롤러 러버트랙 규격 데이터"    : "ROW",
    "용차 차량 노선 데이터"          : "GROUP",   # 실제 시트명으로 수정
    "지입 차량(기사) 노선 데이터"    : "WHOLE",
}

# ── 유틸 ─────────────────────────────────────────────────────────────────────
def clean_val(v) -> str:
    s = str(v).strip()
    return "" if s in ("nan", "None", "NaN", "", "0") else s

def make_hash(text: str, salt: str = "") -> str:
    return hashlib.md5(f"{text}{salt}".encode()).hexdigest()

def extract_material_code(text: str) -> str:
    for pat in [r'자재코드[:\s]*(\d{7})', r'\b(\d{7})\b']:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return ""


# ── 지입기사 노선 전용 : 4명 기사 전원을 1개 문서로 ─────────────────────────
def sheet_to_driver_route_doc(df: pd.DataFrame, sheet_name: str, file_name: str) -> List[Document]:
    """
    지입기사 노선 시트 전용 변환.
    4명 기사 전원의 요일별 납품 동선을 1개 문서로 묶어 검색 누락 방지.
    """
    lines = [
        f"[{sheet_name}]",
        "※ 아래 기사들은 모두 주 5일(월~금) 매일 운행합니다. 요일별 납품 코스(동선)가 다를 뿐입니다.\n"
    ]

    cols = df.columns.tolist()
    driver_col = cols[0]
    day_col    = cols[1] if len(cols) > 1 else None
    dest_col   = cols[2] if len(cols) > 2 else None

    current_driver = None
    for _, row in df.iterrows():
        driver = clean_val(str(row.get(driver_col, "")))
        day    = clean_val(str(row.get(day_col,    ""))) if day_col  else ""
        dest   = clean_val(str(row.get(dest_col,   ""))) if dest_col else ""

        if driver and driver != current_driver:
            current_driver = driver
            driver_clean = driver.replace('\n', ' ')
            lines.append(f"\n## {driver_clean}")
            lines.append("| 요일 | 납품 동선 |")
            lines.append("|------|----------|")

        if day and dest:
            dest_clean = dest.replace('\n', ' / ')
            lines.append(f"| {day} | {dest_clean} |")

    content = "\n".join(lines).strip()
    if len(content) < 30:
        return []
    return [Document(
        page_content=content,
        metadata={"source": file_name, "file_name": file_name,
                  "sheet_name": sheet_name, "strategy": "WHOLE",
                  "file_type": "excel", "doc_type": "driver_route"}
    )]


# ── WHOLE : 시트 전체를 구조화 텍스트 1개 문서로 ────────────────────────────
def sheet_to_whole_doc(df: pd.DataFrame, sheet_name: str, file_name: str) -> List[Document]:
    lines = [f"[{sheet_name}]"]
    for _, row in df.iterrows():
        parts = [clean_val(v) for v in row.values if clean_val(v)]
        if parts:
            lines.append(" | ".join(parts))
    content = "\n".join(lines).strip()
    if len(content) < 30:
        return []
    return [Document(
        page_content=content,
        metadata={"source": file_name, "file_name": file_name,
                  "sheet_name": sheet_name, "strategy": "WHOLE", "file_type": "excel"}
    )]


# ── QA : 질문-답변 쌍 각 1개 문서 ──────────────────────────────────────────
def sheet_to_qa_docs(df: pd.DataFrame, sheet_name: str, file_name: str) -> List[Document]:
    docs = []
    seen = set()
    SKIP = {"[물류팀 운영 규칙]", "구분", ""}

    for _, row in df.iterrows():
        vals = [clean_val(v) for v in row.values if clean_val(v)]
        if not vals:
            continue
        question = vals[0] if len(vals) > 0 else ""
        answer   = vals[1] if len(vals) > 1 else ""

        if question in SKIP:
            continue

        content = f"[{sheet_name}]\nQ: {question}\nA: {answer}" if answer \
                  else f"[{sheet_name}]\n{question}"

        h = make_hash(content)
        if h in seen:
            continue
        seen.add(h)

        docs.append(Document(
            page_content=content,
            metadata={"source": file_name, "file_name": file_name,
                      "sheet_name": sheet_name, "strategy": "QA", "file_type": "excel"}
        ))
    return docs


# ── GROUP : 컬럼 기준 그룹핑 문서 ───────────────────────────────────────────
def sheet_to_group_docs(df: pd.DataFrame, sheet_name: str, file_name: str) -> List[Document]:
    # 첫 데이터 행이 헤더인지 확인 후 컬럼 재설정
    first_row = df.iloc[0].astype(str)
    if first_row.str.contains("구분|출발지|성명", na=False).any():
        df.columns = [clean_val(v) if clean_val(v) else f"col_{i}"
                      for i, v in enumerate(df.iloc[0])]
        df = df.iloc[1:].reset_index(drop=True)

    df.columns = [str(c).strip() if not str(c).startswith("Unnamed") else f"col_{i}"
                  for i, c in enumerate(df.columns)]
    df = df.fillna("")

    group_col = next((c for c in ["구분", "거리 기준", "col_1"] if c in df.columns), None)
    if not group_col:
        return sheet_to_whole_doc(df, sheet_name, file_name)

    docs = []
    seen = set()
    for group_name, group_df in df.groupby(group_col):
        gname = clean_val(group_name)
        if not gname:
            continue

        lines = [f"[{sheet_name} - {gname}]"]
        for _, row in group_df.iterrows():
            parts = [f"{col}: {clean_val(row.get(col,''))}"
                     for col in group_df.columns
                     if col != group_col and clean_val(row.get(col, ""))]
            if parts:
                lines.append("  " + " | ".join(parts))

        content = "\n".join(lines).strip()
        h = make_hash(content)
        if h in seen or len(content) < 20:
            continue
        seen.add(h)

        docs.append(Document(
            page_content=content,
            metadata={"source": file_name, "file_name": file_name, "sheet_name": sheet_name,
                      "group": gname, "strategy": "GROUP", "file_type": "excel"}
        ))
    return docs


# ── ROW : 자재코드 기반 행 단위 문서 ────────────────────────────────────────
PRIORITY_COLS = ["자재코드", "자재내역", "자재 그룹",
                 "주름혹 컨베어벨트 자재코드", "주름혹 컨베어벨트 자재내역",
                 "크롤러 러버트랙 자재코드", "크롤러 러버트랙 자재내역"]

def sheet_to_row_docs(df: pd.DataFrame, sheet_name: str, file_name: str) -> List[Document]:
    docs = []
    seen = set()
    columns = df.columns.tolist()

    for idx, row in df.iterrows():
        parts = []
        for col in PRIORITY_COLS:
            if col in columns:
                v = clean_val(row.get(col, ""))
                if v:
                    parts.append(f"{col}: {v}")
        for col in columns:
            if col in PRIORITY_COLS:
                continue
            v = clean_val(row.get(col, ""))
            if v:
                parts.append(f"{col}: {v}")

        if not parts:
            continue

        content = f"[{sheet_name}]\n" + " | ".join(parts)
        if len(content.strip()) < 20:
            continue

        h = make_hash(content)
        if h in seen:
            continue
        seen.add(h)

        material_code = ""
        for col in PRIORITY_COLS:
            if "코드" in col and col in row.index:
                v = clean_val(row.get(col, ""))
                if re.match(r'^\d{7}$', v):
                    material_code = v
                    break
        if not material_code:
            material_code = extract_material_code(content)

        metadata = {"source": file_name, "file_name": file_name, "sheet_name": sheet_name,
                    "row_number": int(idx) + 1, "strategy": "ROW", "file_type": "excel",
                    "has_material_code": bool(material_code)}
        if material_code:
            metadata["material_code"] = material_code

        docs.append(Document(page_content=content, metadata=metadata))
    return docs


# ── Excel 로더 ────────────────────────────────────────────────────────────────
def load_excel(file_path: str) -> List[Document]:
    file_name = os.path.basename(file_path)
    documents = []

    # 시트별 헤더 행 오버라이드 (0-indexed)
    # 엑셀에서 실제 컬럼 헤더가 0행이 아닌 경우 명시
    HEADER_ROW_OVERRIDE = {
        "물류팀 현황 데이터": 2,   # row 0: 빈 행, row 1: 섹션 타이틀, row 2: 실제 헤더
    }

    try:
        excel_file = pd.ExcelFile(file_path)
        logger.info(f"📊 Excel: {file_name} ({len(excel_file.sheet_names)}개 시트)")

        for sheet_name in excel_file.sheet_names:
            header_row = HEADER_ROW_OVERRIDE.get(sheet_name, 0)
            df = pd.read_excel(file_path, sheet_name=sheet_name,
                               header=header_row).fillna("")
            strategy = SHEET_STRATEGY.get(sheet_name, "ROW")
            logger.info(f"  [{sheet_name}] 전략:{strategy} ({len(df)}행)")

            # 지입기사 노선 시트는 전용 함수 사용 (기사 누락 방지)
            if sheet_name == "지입 차량(기사) 노선 데이터":
                docs = sheet_to_driver_route_doc(df, sheet_name, file_name)
            else:
                fn = {"WHOLE": sheet_to_whole_doc, "QA": sheet_to_qa_docs,
                      "GROUP": sheet_to_group_docs, "ROW": sheet_to_row_docs}[strategy]
                docs = fn(df, sheet_name, file_name)
            logger.info(f"    → {len(docs)}개 문서")
            documents.extend(docs)

    except Exception as e:
        logger.error(f"❌ Excel 로드 실패: {file_name} / {e}")
    return documents


# ── PDF 로더 ─────────────────────────────────────────────────────────────────
def load_pdf(file_path: str) -> List[Document]:
    file_name = os.path.basename(file_path)
    try:
        from langchain_community.document_loaders import PyPDFLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        pages = PyPDFLoader(file_path).load()
        if not pages:
            return []

        # 짧은 페이지 병합 (300자 미만)
        merged, buf = [], ""
        for page in pages:
            text = page.page_content.strip()
            if not text:
                continue
            buf += "\n" + text
            if len(buf) >= 300:
                merged.append(Document(
                    page_content=buf.strip(),
                    metadata={**page.metadata, "file_name": file_name, "file_type": "pdf"}
                ))
                buf = ""
        if buf.strip():
            merged.append(Document(
                page_content=buf.strip(),
                metadata={**pages[-1].metadata, "file_name": file_name, "file_type": "pdf"}
            ))

        chunks = RecursiveCharacterTextSplitter(
            chunk_size=800, chunk_overlap=150,
            separators=["\n\n", "\n", ". ", " ", ""]
        ).split_documents(merged)

        logger.info(f"  ✅ PDF: {file_name} → {len(chunks)}청크")
        return chunks
    except Exception as e:
        logger.error(f"❌ PDF 실패: {file_name} / {e}")
        return []


# ── 전체 문서 로드 ────────────────────────────────────────────────────────────
def load_and_split_documents(data_path: str = "data/source_docs") -> List[Document]:
    logger.info(f"\n{'='*60}\n📁 문서 로딩: {data_path}\n{'='*60}\n")

    pdf_files, excel_files = [], []
    try:
        for f in os.listdir(data_path):
            fp = os.path.join(data_path, f)
            if not os.path.isfile(fp):
                continue
            if f.lower().endswith(".pdf"):
                pdf_files.append(fp)
            elif f.lower().endswith((".xlsx", ".xls")) and not f.startswith("~$"):
                excel_files.append(fp)
    except Exception as e:
        logger.error(f"디렉토리 스캔 실패: {e}")
        return []

    logger.info(f"PDF {len(pdf_files)}개 | Excel {len(excel_files)}개\n")
    documents = []

    if pdf_files:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            for result in as_completed({ex.submit(load_pdf, fp): fp for fp in pdf_files}):
                documents.extend(result.result())

    for fp in excel_files:
        documents.extend(load_excel(fp))

    valid = [d for d in documents if d.page_content and len(d.page_content.strip()) > 15]

    logger.info(f"\n{'='*60}\n✅ 총 {len(valid)}개 유효 문서")
    sc = {}
    for d in valid:
        s = d.metadata.get("strategy", d.metadata.get("file_type", "?"))
        sc[s] = sc.get(s, 0) + 1
    for s, c in sorted(sc.items()):
        logger.info(f"  {s}: {c}개")
    logger.info(f"{'='*60}\n")
    return valid


# ── Qdrant 인덱싱 ─────────────────────────────────────────────────────────────
def batch_embed_and_index(chunks, embeddings, client, collection_name, batch_size=64):
    total = 0
    with tqdm(total=len(chunks), desc="인덱싱", unit="doc") as pbar:
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            try:
                vectors = embeddings.embed_documents([c.page_content for c in batch])
                points = [
                    models.PointStruct(
                        id=make_hash(c.page_content, str(start + i)),
                        vector=v,
                        payload={
                            "page_content": c.page_content,
                            "metadata": c.metadata,
                            # 최상위에도 저장 → Qdrant 버전 무관하게 필터 조회 안정
                            "sheet_name": c.metadata.get("sheet_name", ""),
                            "strategy":   c.metadata.get("strategy", ""),
                            **({"material_code": c.metadata["material_code"]}
                               if c.metadata.get("material_code") else {})
                        }
                    )
                    for i, (c, v) in enumerate(zip(batch, vectors))
                ]
                client.upsert(collection_name=collection_name, points=points)
                total += len(points)
                pbar.update(len(batch))
            except Exception as e:
                logger.error(f"배치 실패(start={start}): {e}")
                for j, chunk in enumerate(batch):
                    try:
                        vec = embeddings.embed_query(chunk.page_content)
                        client.upsert(collection_name=collection_name, points=[
                            models.PointStruct(
                                id=make_hash(chunk.page_content, str(start + j)),
                                vector=vec,
                                payload={"page_content": chunk.page_content,
                                         "metadata": chunk.metadata}
                            )
                        ])
                        total += 1
                    except Exception as ie:
                        logger.error(f"  개별 실패: {ie}")
                pbar.update(len(batch))
    logger.info(f"✅ 인덱싱 완료: {total}개")


def index_documents_to_qdrant(chunks: List[Document]) -> None:
    if not chunks:
        logger.warning("청크 없음")
        return

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    embeddings = OllamaEmbeddings(model=OLLAMA_EMBEDDING_MODEL, base_url=OLLAMA_HOST)

    try:
        sample = embeddings.embed_query("테스트")
        vector_size = len(sample)
    except Exception as e:
        logger.error(f"임베딩 오류: {e}")
        vector_size = 768

    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=500)
    )

    batch_embed_and_index(chunks, embeddings, client, COLLECTION_NAME, VECTOR_BATCH_SIZE)

    info = client.get_collection(COLLECTION_NAME)
    logger.info(f"\n📈 최종 벡터 수: {info.points_count}개")


if __name__ == "__main__":
    DATA_FOLDER = "data/source_docs"
    os.makedirs(DATA_FOLDER, exist_ok=True)
    files = [f for f in os.listdir(DATA_FOLDER)
             if f.lower().endswith((".pdf", ".xlsx", ".xls"))]
    if not files:
        logger.warning(f"'{DATA_FOLDER}'에 PDF/Excel 파일을 넣어주세요.")
    else:
        chunks = load_and_split_documents(DATA_FOLDER)
        if chunks:
            index_documents_to_qdrant(chunks)
        else:
            logger.error("유효 청크 없음")