from django.apps import AppConfig


class SignaturConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "signatur"
    verbose_name = "Digitale Signaturen"

    def ready(self):
        import signatur.signals  # noqa: F401 – Signals registrieren
