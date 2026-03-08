from django.apps import AppConfig


class DatenschutzConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "datenschutz"
    verbose_name = "Datenschutz (DSGVO)"

    def ready(self):
        import datenschutz.signals  # noqa: F401
