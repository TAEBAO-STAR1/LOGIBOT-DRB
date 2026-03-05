from qdrant_client import QdrantClient
from langchain_ollama import OllamaEmbeddings
from config.settings import settings
import re

class LogisticsRetriever:
    def __init__(self):
        self.client = QdrantClient(url=settings.QDRANT_URL)
        self.embeddings = OllamaEmbeddings(model=settings.OLLAMA_EMBEDDING_MODEL, base_url=settings.OLLAMA_HOST)

    def search(self, query: str, limit: int = 5):
        # 자재코드(숫자 7자리 등) 패턴 추출 로직 포함
        query_vector = self.embeddings.embed_query(query)
        return self.client.search(
            collection_name=settings.COLLECTION_NAME,
            query_vector=query_vector,
            limit=limit
        )