from django.apps import AppConfig


class ReceiptsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agent_chat_app.receipts'
    verbose_name = 'Receipt Processing'
    
    def ready(self):
        """Initialize app-specific settings and signals."""
        try:
            import agent_chat_app.receipts.signals  # noqa: F401
        except ImportError:
            pass
