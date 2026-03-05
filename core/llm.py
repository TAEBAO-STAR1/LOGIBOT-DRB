import requests
import json
import logging
from typing import Any, List, Optional, Dict
from langchain_core.language_models.llms import LLM
from pydantic import Field
from config.settings import settings

logger = logging.getLogger(__name__)

class OnPremiseLLM(LLM):
    model_name: str = Field(default=settings.ONPREMISE_MODEL)
    url: str = Field(default=settings.ONPREMISE_API_URL)

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any) -> str:
        # 1. 요청 페이로드 구성 (OpenAI 호환 포맷으로 교정)
        # 400 에러는 보통 'messages' 구조나 'model' 이름이 틀렸을 때 발생합니다.
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "당신은 물류 전문가입니다."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 1024
        }
        
        headers = {"Content-Type": "application/json"}

        try:
            # 2. API 호출
            response = requests.post(
                self.url, 
                headers=headers,
                json=payload, 
                timeout=settings.ONPREMISE_TIMEOUT
            )
            
            # 에러 발생 시 상세 정보 로깅 (400 에러 원인 파악용)
            if response.status_code != 200:
                logger.error(f"LLM API Error {response.status_code}: {response.text}")
                return f"에러 발생: 서버가 요청을 거절했습니다. ({response.status_code})"

            # 3. 응답 파싱 (응답 구조에 따라 선택)
            resp_json = response.json()
            
            # OpenAI 호환 형식일 경우
            if 'choices' in resp_json:
                return resp_json['choices'][0]['message']['content']
            # Ollama /api/generate 형식일 경우
            elif 'response' in resp_json:
                return resp_json['response']
            else:
                return "응답 형식이 올바르지 않습니다."

        except Exception as e:
            logger.error(f"❌ LLM 호출 중 예외 발생: {str(e)}")
            return f"시스템 오류가 발생했습니다: {str(e)}"

    @property
    def _llm_type(self) -> str:
        return "on_premise_llm"