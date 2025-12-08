# 📦 DRB LOGIBOT-AI

> 물류팀을 위한 지능형 RAG 기반 AI 챗봇 시스템


## 🌟 주요 기능

- 🤖 RAG 기반 지능형 응답: Qdrant 벡터 DB와 온프레미스 LLM을 활용한 정확한 답변 생성
- 📚 누적 학습 시스템: Good/Bad 피드백을 통한 지속적인 답변 품질 개선
- 🌐 하이브리드 검색: 로컬 DB 검색 실패 시 자동으로 웹 검색으로 전환
- 💬 대화 관리: 여러 대화 세션을 저장하고 관리
- 📊 피드백 시스템: 사용자 피드백 기반 학습 데이터 품질 관리
- 🎨 직관적인 UI: 다크 테마의 현대적인 채팅 인터페이스

## 🏗️ 시스템 아키텍처

```
┌─────────────────┐
│  Streamlit UI   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│  Query Processor│◄────►│ Learning Sys │
└────────┬────────┘      └──────────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌───────┐
│Qdrant  │ │Web    │
│Vector  │ │Search │
│DB      │ │(DDG)  │
└────────┘ └───────┘
    │
    ▼
┌─────────────────┐
│ OnPremise LLM   │
│ (Gemma 27B)     │
└─────────────────┘
```

## 🚀 빠른 시작

### 필수 요구사항

- Python 3.8 이상
- Docker (Qdrant 실행용)
- 최소 16GB RAM (LLM 실행 시)
- CUDA 지원 GPU (선택사항, 성능 향상)

### 설치 방법

1. 저장소 클론
```bash
git clone https://github.com/your-username/drb-logibot-ai.git
cd drb-logibot-ai
```

2. Python 가상환경 생성
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. 의존성 패키지 설치
```bash
pip install -r requirements.txt
```

4. 환경 변수 설정
```bash
cp .env.example .env
# .env 파일을 편집하여 필요한 설정 입력
```

5. Qdrant 벡터 DB 실행
```bash
docker run -p 6333:6333 -p 6334:6334 \
    -v $(pwd)/qdrant_storage:/qdrant/storage \
    qdrant/qdrant
```

6. Ollama 설치 및 임베딩 모델 다운로드
```bash
# Ollama 설치 (https://ollama.ai/)
ollama pull granite-embedding:278m
```

7. 애플리케이션 실행
```bash
streamlit run app.py
```


브라우저에서 `http://localhost:8501` 접속

## ⚙️ 환경 설정

`.env` 파일에서 다음 설정을 구성하세요:

```env
# Qdrant 설정
QDRANT_HOST=http://localhost:6333
QDRANT_COLLECTION=logistics_data
LEARNING_COLLECTION=learning_history
BAD_FEEDBACK_COLLECTION=bad_feedback_history

# LLM 설정
ONPREMISE_API_URL=http://192.168.1.120:11435/v1/chat/completions
ONPREMISE_MODEL=ISTA-DASLab/gemma-3-27b-it-GPTQ-4b-128g
ONPREMISE_TIMEOUT=60

# Ollama 설정
OLLAMA_HOST=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=granite-embedding:278m
```

## 📁 프로젝트 구조

```
drb-logibot-ai/
├── app.py                      # Streamlit 메인 애플리케이션
├── rag_pipeline/
│   ├── __init__.py
│   └── query_processor.py      # RAG 로직 및 학습 시스템
├── data/                       # 물류 문서 데이터
├── qdrant_storage/             # Qdrant 데이터 저장소
├── requirements.txt            # Python 의존성
├── .env.example               # 환경 변수 템플릿
└── README.md                  # 프로젝트 문서
```

## 💡 사용 방법

### 1. 기본 질문하기
```
사용자: "컨베이어 벨트 유지보수 절차는?"
봇: [구조화된 답변 + 참고 문서]
```

### 2. 피드백 제공
- 답변이 유용한 경우: 👍 버튼 클릭
- 답변이 부정확한 경우: 👎 버튼 클릭

### 3. 대화 관리
- 새 대화: 사이드바에서 "새 대화 시작" 클릭
- 대화 전환: 사이드바에서 이전 대화 선택
- 대화 삭제: 현재 대화의 🗑️ 버튼 클릭
- 대화 이름 변경: 현재 대화의 ✏️ 버튼 클릭

### 4. 대화 내보내기
사이드바 하단의 "현재 대화 내보내기" 버튼으로 JSON 형식 저장

## 🧠 학습 시스템

### Good 피드백 (👍)
- `learning_history` 컬렉션에 저장
- 유사한 질문 발생 시 재활용
- 재사용 횟수 추적 및 품질 점수 업데이트

### Bad 피드백 (👎)
- `bad_feedback_history` 컬렉션에 별도 저장
- 관리자 리뷰를 위한 pending 상태 유지
- 문제 패턴 분석을 위한 데이터 축적

## 🔧 고급 설정

### 커스텀 LLM 사용
`query_processor.py`의 `OnPremiseGemmaLLM` 클래스를 수정하여 다른 LLM 통합 가능

### 프롬프트 커스터마이징
`PROMPT_TEMPLATE` 변수를 수정하여 답변 스타일 조정

### 검색 파라미터 조정
```python
# 유사도 임계값 변경
filtered_docs = [(doc, score) for doc, score in docs_with_scores if score >= 0.4]

# 검색 결과 개수 변경
docs_with_scores = rag_chain.vectorstore.similarity_search_with_score(query, k=5)
```

## 📊 성능 최적화

### 권장 사항
1. GPU 활용: CUDA 지원 GPU 사용 시 추론 속도 10배 향상
2. 캐싱: 자주 묻는 질문은 Redis 캐싱 권장
3. 배치 처리: 대량 문서 임베딩 시 배치 크기 조정
4. 벡터 차원: 임베딩 모델에 따라 적절한 차원 선택

### 성능 메트릭
- 평균 응답 시간: ~3-5초
- 벡터 검색 시간: ~100-200ms
- LLM 추론 시간: ~2-4초

## 🐛 문제 해결

### Qdrant 연결 오류
```bash
# Qdrant 컨테이너 상태 확인
docker ps | grep qdrant

# 로그 확인
docker logs <container_id>
```

### LLM API 타임아웃
- `.env`에서 `ONPREMISE_TIMEOUT` 값 증가
- 네트워크 연결 및 방화벽 설정 확인

### 임베딩 오류
```bash
# Ollama 서비스 상태 확인
ollama list

# 모델 재다운로드
ollama pull granite-embedding:278m
```

## 🤝 기여 방법

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 👥 개발팀

- 프로젝트 리드: [Your Name](https://github.com/your-username)
- 이메일: your.email@example.com

## 🙏 감사의 말

- [Streamlit](https://streamlit.io/) - 웹 인터페이스 프레임워크
- [Qdrant](https://qdrant.tech/) - 벡터 데이터베이스
- [LangChain](https://langchain.com/) - LLM 오케스트레이션
- [Ollama](https://ollama.ai/) - 로컬 LLM 실행 플랫폼

## 📈 로드맵

- [ ] 다국어 지원 (영어, 중국어)
- [ ] 음성 입력/출력 기능
- [ ] 대시보드 및 분석 기능
- [ ] 모바일 앱 개발
- [ ] API 엔드포인트 제공
- [ ] 클라우드 배포 가이드

## 📞 문의

---

⭐ 이 프로젝트가 도움이 되셨다면 Star를 눌러주세요!