# arbeitszeit/signals.py
"""
Django Signals für automatische Berechnungen
"""

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone
from .models import MonatlicheArbeitszeitSoll


@receiver(user_logged_in)
def auto_berechne_soll_stunden(sender, request, user, **kwargs):
    """
    Berechnet automatisch Soll-Stunden beim Login,
    wenn für den aktuellen Monat noch keine vorhanden sind.
    
    Args:
        sender: Die Klasse die das Signal gesendet hat
        request: Das HttpRequest-Objekt
        user: Der eingeloggte User
        **kwargs: Weitere Signal-Parameter
    """
    # Prüfe ob User ein Mitarbeiter ist
    if not hasattr(user, 'mitarbeiter'):
        return
    
    mitarbeiter = user.mitarbeiter
    heute = timezone.now().date()
    
    # Prüfe ob bereits berechnet
    existiert = MonatlicheArbeitszeitSoll.objects.filter(
        mitarbeiter=mitarbeiter,
        jahr=heute.year,
        monat=heute.month
    ).exists()
    
    if not existiert:
        # Automatisch berechnen
        try:
            MonatlicheArbeitszeitSoll.berechne_und_speichere(
                mitarbeiter,
                heute.year,
                heute.month
            )
            print(f"[OK] Auto-Berechnung: Soll-Stunden fuer {mitarbeiter.vollname} berechnet ({heute.strftime('%B %Y')})")
        except Exception as e:
            print(f"[WARN] Auto-Berechnung fehlgeschlagen fuer {mitarbeiter.vollname}: {e}")
