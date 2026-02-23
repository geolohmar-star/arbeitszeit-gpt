from django.apps import AppConfig


class FormulareConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "formulare"
    verbose_name = "Formulare"

    def ready(self):
        """Import signals when app is ready."""
        import formulare.signals  # noqa
