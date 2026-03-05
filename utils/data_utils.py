import re
import hashlib

def clean_text(text: str) -> str:
    """불필요한 공백 및 특수문자 정제"""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def generate_doc_id(content: str) -> str:
    """콘텐츠 기반 유니크 ID 생성 (중복 방지)"""
    return hashlib.md5(content.encode()).hexdigest()

def is_material_code(text: str) -> bool:
    """자재코드 형식(예: 7자리 숫자 등) 확인"""
    return bool(re.match(r'^\d{7,10}$', text))