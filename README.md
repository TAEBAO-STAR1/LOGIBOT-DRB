# LOGIBOT — DRB 동일고무벨트 물류팀 AI 어시스턴트

DRB 동일고무벨트 물류팀 전용 사내 RAG 기반 AI 챗봇.  
자재 조회, 기사 납품 동선, 운영규칙 Q&A, 배차 계산을 채팅 하나로 처리합니다.

---

## 기능 개요

| 기능 | 설명 |
|---|---|
| 자재 조회 | 자재코드 7자리 입력 시 규격·중량·배차 정보 즉시 반환 |
| 기사 납품 동선 | 지입기사별 요일별 납품 동선, 격주 교대 자동 판별 |
| 운영규칙 Q&A | 물류팀 운영규칙 51개 항목 자연어 질의응답 |
| 담당자 조회 | 공정별 담당자·내선번호·클레임 문의처 |
| 컨베어벨트 직경 계산 | PLY·고무두께 기반 롤 직경 자동 계산 |
| 배차 시뮬레이터 | 국내운임비교 / 수출포장량 / 컨베어벨트배차 / 국내최적배차 |
| 국내 운송방식 | 총중량·도착지 기준 직송·화물·택배 자동 추천 |
| 수출 포장량 | 자재그룹(B01/B02/N18/N19)별 박스 수량 자동 계산 |

---

## 기술 스택

```
Frontend     Streamlit
RAG          LangChain
LLM          gpt-oss-120b (On-Premise :9800)
Embedding    granite-embedding:278m (Ollama :11434)
Vector DB    Qdrant (On-Premise :6333)
Data         Excel V5 (.xlsx) — 12개 시트
Language     Python 3.12
```

---

## 프로젝트 구조

```
Logibot-DRB/
├── app.py                          # Streamlit 메인 앱 (UI + 시뮬레이터)
├── .env                            # 환경변수 (Git 제외)
├── requirements.txt
└── rag_pipeline/
    ├── query_processor.py          # RAG 쿼리 처리 (도메인 분류·검색·LLM 생성)
    ├── data_loader.py              # Excel → Qdrant 적재 파이프라인
    ├── 3D.py                       # 3D 적재 시뮬레이터 (Plotly)
    └── data/
        └── source_docs/
            ├── Logibot-Data(기본)_V5.xlsx   # 메인 데이터 (Git 제외)
            └── 운임_테이블.xlsx              # 운임 데이터 (Git 제외)
```

---

## 설치 및 실행

### 1. 패키지 설치

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env` 파일을 프로젝트 루트에 생성합니다.

```env
# LLM 서버
LLM_BASE_URL=http://localhost:9800
LLM_MODEL=gpt-oss-120b

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=logistics_data

# Ollama 임베딩
OLLAMA_HOST=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=granite-embedding:278m

# 데이터 파일 경로
LOGIBOT_EXCEL_PATH=rag_pipeline/data/source_docs/Logibot-Data(기본)_V5.xlsx
LOGIBOT_FARE_PATH=rag_pipeline/data/source_docs/운임_테이블.xlsx
```

### 3. Qdrant 데이터 적재

처음 실행하거나 Excel 데이터가 변경된 경우 실행합니다.

```bash
cd rag_pipeline
python data_loader.py --reset
```

적재 완료 후 로그 확인:
```
INFO - 차량 후보 10개 (Qdrant 파싱)        ← 차량 데이터 정상
INFO - 운임 테이블: N건 적재 완료           ← 운임 데이터 정상
```

### 4. 앱 실행

```bash
# 프로젝트 루트에서 실행
streamlit run app.py
```

---

## 데이터 구조 (Excel V5 — 12개 시트)

| 시트명 | 도메인 | 설명 |
|---|---|---|
| 물류팀 운영 규칙 | operation_rule | Q&A 51개 항목 |
| 지입 차량(기사) 노선 데이터 | driver_route | 기사별 요일별 납품 동선, A/B/공통 그룹 |
| 물류팀 현황 데이터 | personnel | 팀원 28명 직책·담당공정·내선번호 |
| 차량 데이터 | vehicle | 차량 10종 최대중량·적재함 스펙 |
| 컨베어벨트 규격 데이터 | conveyor | 자재코드별 PLY·고무두께·포규격 |
| 크롤러 러버트랙 규격 데이터 | crawler | 자재코드별 1PC중량·PLT적재수 |
| 용차 차량 노선 데이터 | domestic | 권역별 거리기준·소요시간 |
| 포장량 산출 데이터 | export | B01/B02/N18/N19 박스당 중량 |
| 수출 포장량 산출 수식 | export | 포장량 계산 공식 |
| 주름혹벨트 우든박스 사이즈 데이터 | sidewall | 자재코드별 우든박스 규격 |
| 파렛트, 박스 데이터 | pallet_box | 공정별 PLT·BOX 포장재 규격 |
| 컨베어벨트 직경 산출 수식 | conveyor | 롤 직경 계산 공식 |

---

## 검색 구조 (3단 레이어)

```
질문 입력
  │
  ├─ 시뮬레이터 키워드 매칭 → 해당 시 즉시 유도 메시지 반환 (LLM 미호출)
  │
  └─ Layer 1: 도메인 분류 (_detect_domain)
       8개 도메인 키워드 우선순위 판별 + 자재코드 7자리 감지
       │
       └─ Layer 2: 하이브리드 검색 (hybrid_search)
            코드 검색(Qdrant filter) → 벡터 검색(k=50, 임계값 0.15~0.20)
            → 도메인 강제 보완(fetch_whole_docs) → Fallback(임계값 0.10)
            │
            └─ Layer 3: 컨텍스트 조립 + LLM 생성
                 도메인별 context limit (4,000 / 6,000 / 8,000자)
                 → get_domain_prompt → gpt-oss-120b → 답변 반환

특수 처리:
  - 기사 노선: LLM 미사용, Python 직접 포맷팅
  - 운임 계산: calculate_fare_comparison() 직접 계산
  - Excel Fallback: Qdrant 문서 18개 미만 시 직접 조회
```

---

## 격주 기사 교대 기준

중부물류센터 지입기사(이용구/심효섭)는 격주로 노선이 교대됩니다.

```python
BIWEEKLY_ANCHOR = date(2026, 5, 25)  # B주 기준 (이용구 운행)
# weeks_elapsed % 2 == 0 → B주(이용구) / 홀수 → A주(심효섭)
```

---

## 주요 변경 이력

| 버전 | 내용 |
|---|---|
| V5 | 격주 로직 버그 수정, 운영규칙 summary 청크 추가, 도메인 분류 개선(operation_rule / vehicle / pallet_box / sidewall), 시뮬레이터 유도 컨베어벨트배차 추가, context limit 도메인별 차등, 차량 파싱 skip 버그 수정, 운임 테이블 .env 지원 |
| V4 | 초기 RAG 구조, 7개 도메인, 17개 단일 프롬프트 |

---

## 참고

- 임베딩 모델: [granite-embedding](https://ollama.com/library/granite-embedding) (768차원)
- 벡터 DB: [Qdrant](https://qdrant.tech/)
---
