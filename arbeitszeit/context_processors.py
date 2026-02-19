"""
Context Processors fuer die arbeitszeit-App.
Stellt globale Template-Variablen fuer alle Views bereit.
"""


def schichtplan_zugang(request):
    """Prueft ob der eingeloggte User Zugang zur Schichtplanung hat.

    Gibt die Variable 'hat_schichtplan_zugang' ans Template weiter.
    Superuser bekommen automatisch Zugang, alle anderen benoetigen
    die explizite Permission 'schichtplan.schichtplan_zugang'.
    """
    if not request.user.is_authenticated:
        return {"hat_schichtplan_zugang": False}

    if request.user.is_superuser:
        return {"hat_schichtplan_zugang": True}

    # Frische DB-Abfrage ohne Permission-Cache
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    try:
        from schichtplan.models import Schichtplan
        ct = ContentType.objects.get_for_model(Schichtplan)
        perm = Permission.objects.get(codename="schichtplan_zugang", content_type=ct)
        hat_zugang = (
            request.user.user_permissions.filter(id=perm.id).exists()
            or request.user.groups.filter(permissions=perm).exists()
        )
    except Exception:
        hat_zugang = False

    return {"hat_schichtplan_zugang": hat_zugang}


def genehmiger_rolle(request):
    """Prueft ob der eingeloggte User Genehmiger fuer mindestens einen
    Mitarbeiter ist (guardian-Permission 'genehmigen_antraege').

    Gibt 'hat_genehmiger_rolle' ans Template weiter.
    """
    if not request.user.is_authenticated:
        return {"hat_genehmiger_rolle": False}

    if request.user.is_superuser or request.user.is_staff:
        return {"hat_genehmiger_rolle": True}

    try:
        from guardian.shortcuts import get_objects_for_user
        from arbeitszeit.models import Mitarbeiter
        hat_rolle = get_objects_for_user(
            request.user,
            "genehmigen_antraege",
            Mitarbeiter,
        ).exists()
    except Exception:
        hat_rolle = False

    return {"hat_genehmiger_rolle": hat_rolle}
