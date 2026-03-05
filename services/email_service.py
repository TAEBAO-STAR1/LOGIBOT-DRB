import smtplib
from email.mime.text import MIMEText
from config.settings import settings

class EmailService:
    @staticmethod
    def send_bad_feedback_alert(query, answer):
        if not settings.EMAIL_ENABLED: return
        msg = MIMEText(f"부정 피드백 발생\n질문: {query}\n답변: {answer}")
        msg['Subject'] = "[경고] 챗봇 부정 피드백 알림"
        msg['From'] = settings.EMAIL_FROM
        msg['To'] = settings.EMAIL_TO
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)