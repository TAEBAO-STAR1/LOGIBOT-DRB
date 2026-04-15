# LOGIBOT — Claude Code Context

## 프로젝트 개요

LOGIBOT은 DRB 사내 물류팀을 위한 **RAG 기반 AI 챗봇**입니다.
Excel 데이터(크롤러/고무트랙 스펙, 컨베어벨트, 차량 데이터, 물류 규칙 등)를
Qdrant 벡터 DB에 인덱싱하고, Ollama 로컬 LLM으로 질의응답을 수행합니다.

- **팀 모드:** 국내영업 / 해외영업 / 트랙영업 (사이드바에서 선택)
- **주요 기능:** 하이브리드 RAG 검색, 차량 배차 시뮬레이터, 수출 포장 계산기, 용차 기사 라우팅, 피드백 시스템

---

## 기술 스택

| 구분 | 내용 |
|------|------|
| Frontend / App | Streamlit |
| LLM | gpt-oss-120b (온프레미스, Ollama) |
| Embeddings | `granite-embedding:278m` (Ollama) |
| Vector DB | Qdrant |
| 데이터 소스 | Excel (`Logibot-Data_기본__V4.xlsx`), PDF (컨테이너 스펙) |
| 언어 | Python 3.x |

---

## 디렉토리 구조

```
logibot/
├── app.py                          # Streamlit 메인 앱 (~1800줄)
│                                   # - UI 레이아웃, 세션 상태 관리
│                                   # - 팀 모드 전환 (국내/해외/트랙영업)
│                                   # - 채팅 인터페이스, 피드백 UI
│
├── query_processor.py              # RAG 핵심 파이프라인 (~2000줄)
│                                   # - _detect_domain(): 도메인 라우팅
│                                   #   (domestic / crawler / export / vehicle 등)
│                                   # - hybrid_search(): 벡터 + 키워드 검색
│                                   # - get_db_transport_advice(): 차량 추천 로직
│                                   # - 물류 운영 규칙, 수출 포장, 라우팅 처리
│
├── data_loader.py                  # 데이터 인덱서 (~470줄)
│                                   # - Excel 12개 시트 파싱 및 Qdrant 업로드
│                                   # - PDF 컨테이너 스펙 파싱
│
├── Logibot-Data_기본__V4.xlsx      # 주요 데이터 소스
│                                   # 시트 목록:
│                                   # - 크롤러/고무트랙 스펙
│                                   # - 컨베어벨트 스펙
│                                   # - 사이드월 벨트 스펙
│                                   # - 차량 데이터
│                                   # - 물류 운영 규칙
│                                   # - 수출 포장 규칙
│                                   # - 용차 기사 라우트 데이터
│                                   # (총 12개 시트)
│
├── *.pdf                           # 컨테이너 스펙 문서
└── requirements.txt                # 패키지 의존성
```

---

## 환경 변수 / 설정

```bash
# Qdrant
QDRANT_HOST=localhost          # 또는 온프레미스 서버 주소
QDRANT_PORT=6333
QDRANT_COLLECTION=logistics_data   # 메인 컬렉션명 (중요: 하드코딩 금지)

# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma3:27b-instruct-q4_K_M   # 실제 모델명 확인 필요
OLLAMA_EMBED_MODEL=granite-embedding:278m
```

> ⚠️ `QDRANT_COLLECTION` 은 환경변수로 관리. `query_processor.py` 내부에서
> `collection_name` 하드코딩 절대 금지.

---

## 핵심 로직 & 주의사항

### 1. 도메인 라우팅 (`_detect_domain`)
- 쿼리를 분석해 도메인을 판별: `domestic` / `crawler` / `export` / `vehicle` / `general`
- **주의:** `domestic` 도메인 누락 시 국내 배송 쿼리가 `crawler` 로 오라우팅됨
- 키워드 기반 + LLM 보조 판별 방식

### 2. 차량 추천 로직 (`get_db_transport_advice`)
- PLT 수량 + **중량 제약** 동시 고려 필수
- 정렬 기준: PLT 수량만으로 정렬 금지 → 중량 초과 차량 필터링 선행
- Qdrant 필터 키: 최상위 `sheet_name` 필드 사용 (❌ `metadata.sheet_name`)
- 두 번 조회(two-pass lookup) 패턴 유지

### 3. 하이브리드 검색 (`hybrid_search`)
- 자재 코드 포함 쿼리 시 물류 운영 규칙 시트 반드시 로드
- 벡터 검색 + 키워드 필터 병행

### 4. 팀 모드별 동작 차이
| 모드 | 주요 기능 |
|------|-----------|
| 국내영업 | 국내 배송, 차량 배차, 물류 규칙 |
| 해외영업 | 수출 포장 계산, 컨테이너 스펙 |
| 트랙영업 | 크롤러/고무트랙 스펙 조회 |

---

## 자주 쓰는 명령어

```bash
# 앱 실행
streamlit run app.py

# 데이터 인덱싱 (Qdrant에 Excel/PDF 업로드)
python data_loader.py

# Qdrant 서버 실행 (Docker)
docker run -p 6333:6333 qdrant/qdrant

# Ollama 모델 확인
ollama list
ollama run gemma3:27b-instruct-q4_K_M
```

---

## 코딩 규칙

1. **함수 수정 전** `query_processor.py` 전체 흐름을 먼저 파악할 것
2. **Qdrant 필터** 수정 시 반드시 `sheet_name` 키 레벨 확인 (top-level vs metadata)
3. **환경변수** 우선 — 설정값 하드코딩 금지
4. **팀 모드** 분기 로직은 `app.py` 에서만 처리, `query_processor.py` 는 모드 값을 인자로 받는 구조 유지
5. 새 시트 추가 시 `data_loader.py` 파싱 로직 + `hybrid_search()` 라우팅 동시 업데이트
6. 한국어 응답 기본 원칙 — 프롬프트에서 언어 강제 설정 유지

---

## 알려진 버그 & 수정 이력

| 파일 | 함수 | 문제 | 상태 |
|------|------|------|------|
| query_processor.py | `_detect_domain()` | `domestic` 도메인 누락 → 배송 쿼리 오라우팅 | ✅ 수정됨 |
| query_processor.py | `get_db_transport_advice()` | PLT 수량만 정렬, 중량 제약 무시 | ✅ 수정됨 |
| query_processor.py | `hybrid_search()` | 자재 코드 쿼리 시 물류 규칙 시트 미로드 | ✅ 수정됨 |
| query_processor.py | `get_db_transport_advice()` | `collection_name` 하드코딩 + 잘못된 Qdrant 필터 키 | ✅ 수정됨 |

---

## 참고

- Excel 시트 구조 변경 시 → `data_loader.py` 파싱 로직 수정 후 **재인덱싱 필수**
- Qdrant 컬렉션 초기화 후에는 반드시 `data_loader.py` 재실행
- 모델 변경 시 `OLLAMA_MODEL` 환경변수만 수정 (코드 수정 불필요)