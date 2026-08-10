from app.core.config import get_settings


def build_celery_app() -> object:
    from celery import Celery

    settings = get_settings()
    broker = settings.celery_broker_url or settings.redis_url
    backend = settings.celery_result_backend or settings.redis_url
    app = Celery(
        "argus",
        broker=broker,
        backend=backend,
        include=["app.workers.tasks"],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        worker_prefetch_multiplier=1,
        beat_schedule={
            "poll-all-vendors": {
                "task": "argus.poll_all_vendors",
                "schedule": 6 * 60 * 60.0,
            }
        },
    )
    return app


app = build_celery_app()


def register_tasks() -> None:
    from app.workers import tasks

    app.task(name="argus.run_detection")(tasks.run_detection)
    app.task(name="argus.scan_and_fix")(tasks.scan_and_fix)
    app.task(name="argus.register_repository")(tasks.register_repository)
    app.task(name="argus.poll_all_vendors")(tasks.poll_all_vendors)


register_tasks()