from qdrant_client import QdrantClient
from config.settings import settings
from datetime import datetime

class LearningSystem:
    def __init__(self):
        self.client = QdrantClient(url=settings.QDRANT_URL)

    def save_feedback(self, query, answer, score):
        self.client.upsert(
            collection_name=settings.BAD_FEEDBACK_COLLECTION if score == 0 else settings.LEARNING_COLLECTION,
            points=[{"id": int(datetime.now().timestamp()), "vector": [0]*768, "payload": {"query": query, "answer": answer}}]
        )