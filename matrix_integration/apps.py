from django.apps import AppConfig


class MatrixIntegrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "matrix_integration"
    verbose_name = "Matrix / Element"

    def ready(self):
        import matrix_integration.signals  # noqa: F401
