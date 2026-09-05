def get_celery_app():
    from app.workers.celery_app import app
    return app
