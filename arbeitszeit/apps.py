from django.apps import AppConfig



class ArbeitszeitConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'arbeitszeit'

class ArbeitszeitConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'arbeitszeit'
    verbose_name = 'Arbeitszeit-Verwaltung'
    
    def ready(self):
        """Signals beim App-Start importieren"""
        import arbeitszeit.signals  # noqa
