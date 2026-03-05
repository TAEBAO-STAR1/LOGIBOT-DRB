from core.processor import QueryProcessor
from services.email_service import EmailService
from services.learning_system import LearningSystem
from utils.logger import get_logger

logger = get_logger("Main")

class LogisticsAgent:
    def __init__(self):
        self.processor = QueryProcessor()
        self.learning = LearningSystem()

    def ask(self, query: str, history: list = []):
        logger.info(f"질문 수신: {query}")
        result = self.processor.get_response(query, history)
        return result

    def feedback(self, query, answer, score):
        self.learning.save_feedback(query, answer, score)
        if score == 0:
            EmailService.send_bad_feedback_alert(query, answer)
            logger.warning("부정 피드백으로 인한 이메일 발송")

if __name__ == "__main__":
    agent = LogisticsAgent()
    # 테스트 실행
    response = agent.ask("6004010 자재 위치 알려줘")
    print(f"AI 답변: {response['answer']}")