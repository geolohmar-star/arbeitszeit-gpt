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


def workflow_tasks_anzahl(request):
    """Zaehlt offene Workflow-Tasks fuer den eingeloggten User.

    Gibt 'workflow_tasks_anzahl' ans Template weiter – wird in der Navbar
    als Badge am Arbeitsstapel-Link angezeigt.
    Zaehlt Tasks die direkt oder ueber die Stelle des Users zugewiesen sind.
    """
    if not request.user.is_authenticated:
        return {"workflow_tasks_anzahl": 0}

    try:
        from django.db.models import Q
        from workflow.models import WorkflowTask

        user = request.user

        tasks_direkt = Q(zugewiesen_an_user=user)

        tasks_stelle = Q(zugewiesen_an_user__isnull=True)
        if (
            hasattr(user, "hr_mitarbeiter")
            and user.hr_mitarbeiter
            and user.hr_mitarbeiter.stelle
        ):
            tasks_stelle &= Q(zugewiesen_an_stelle=user.hr_mitarbeiter.stelle)
        else:
            tasks_stelle = Q(pk__isnull=True)

        anzahl = WorkflowTask.objects.filter(
            tasks_direkt | tasks_stelle,
            status__in=["offen", "in_bearbeitung"],
        ).count()
    except Exception:
        anzahl = 0

    return {"workflow_tasks_anzahl": anzahl}


def team_stapel_anzahl(request):
    """Zaehlt offene, noch nicht geclaimte Team-Queue-Tasks in den Teams des Users.

    Gibt 'team_stapel_anzahl' ans Template weiter – wird in der Navbar
    als Badge am Team-Stapel-Link angezeigt.
    """
    if not request.user.is_authenticated:
        return {"team_stapel_anzahl": 0}

    try:
        from formulare.models import TeamQueue
        from workflow.models import WorkflowTask

        user_teams = list(
            TeamQueue.objects.filter(mitglieder=request.user).values_list("pk", flat=True)
        )
        if not user_teams:
            return {"team_stapel_anzahl": 0}

        anzahl = WorkflowTask.objects.filter(
            zugewiesen_an_team_id__in=user_teams,
            status="offen",
            claimed_von__isnull=True,
        ).count()
    except Exception:
        logger.exception("team_stapel_anzahl Processor Fehler fuer User %s", request.user)
        anzahl = 0

    return {"team_stapel_anzahl": anzahl}


def hilfe_kontext(request):
    """Stellt die App-Liste fuer das Hilfe-Modal bereit."""
    return {
        "apps_liste": [
            "arbeitszeit", "formulare", "schichtplan", "hr", "workflow",
            "facility", "raumbuch", "signatur", "datenschutz", "dokumente",
            "berechtigungen", "veranstaltungen",
        ]
    }
