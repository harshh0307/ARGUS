from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_app = None


def _get_app():
    global _app
    if _app is not None:
        return _app
    try:
        from celery import Celery

        from app.core.config import get_settings

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
                "evaluate-drift-events": {
                    "task": "argus.evaluate_drift_events",
                    "schedule": 300.0,
                },
                "sync-changelogs": {
                    "task": "argus.sync_changelogs",
                    "schedule": 6 * 60 * 60.0,
                },
                "sync-installation-repos": {
                    "task": "argus.sync_all_installation_repos",
                    "schedule": 1 * 60 * 60.0,
                },
            },
        )
        _app = app
        return app
    except ImportError:
        logger.warning("celery is not installed; task queue disabled")
        return None
    except Exception:
        logger.exception("failed to build celery app")
        return None


class _CeleryProxy:
    """Lazy proxy that defers celery import until first use."""

    def __getattr__(self, name):
        inner = _get_app()
        if inner is None:
            raise ImportError("celery is not installed")
        return getattr(inner, name)


app = _CeleryProxy()
