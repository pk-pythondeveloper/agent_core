from celery import Celery
from app.config import settings

celery_app = Celery("agentcore", broker=settings.celery_broker_url, backend=settings.celery_result_backend, include=["app.tasks"])
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", task_acks_late=True)
