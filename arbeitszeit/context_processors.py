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


def cmd_items(request):
    """Baut die Schnellsuche-Eintraege fuer die Navbar-Befehlspalette.

    Gibt 'cmd_items_json' (Python-Liste) ans Template weiter.
    Das Template rendert sie per {{ cmd_items_json|json_script:"cmd-items-data" }}
    als CSP-sicheres JSON-Datentag.
    """
    if not request.user.is_authenticated:
        return {"cmd_items_json": []}

    u = request.user

    def url(name, *args):
        from django.urls import reverse, NoReverseMatch
        try:
            return reverse(name, args=args)
        except NoReverseMatch:
            return "#"

    # Berechtigungen ermitteln
    hat_genehmiger = u.is_staff or u.is_superuser or getattr(u, "hat_genehmiger_rolle", False)
    try:
        hat_genehmiger = hat_genehmiger or request.hat_genehmiger_rolle
    except AttributeError:
        pass

    ist_facility = getattr(request, "ist_facility_mitglied", False)
    ist_vorg = getattr(request, "ist_vorgesetzter", False)
    hat_schicht = getattr(request, "hat_schichtplan_zugang", False)
    ist_fk = getattr(request, "ist_fuehrungskraft", False)
    al_anzahl = getattr(request, "al_queue_anzahl", 0)
    ist_facility_oder_staff = ist_facility or u.is_staff

    items = [
        {"l": "Dashboard",                  "u": url("arbeitszeit:dashboard"),                         "g": "Allgemein"},
        {"l": "Arbeitsstapel",               "u": url("workflow:arbeitsstapel"),                        "g": "Aufgaben"},
        {"l": "Team-Stapel",                 "u": url("formulare:team_queue"),                          "g": "Aufgaben"},
        {"l": "Antraege / Neuer Antrag",     "u": url("formulare:dashboard"),                           "g": "Antraege"},
        {"l": "Soll-Stunden Monat",          "u": url("arbeitszeit:soll_stunden_dashboard"),            "g": "Personal"},
        {"l": "Soll-Stunden Jahr",           "u": url("arbeitszeit:soll_stunden_jahresuebersicht"),     "g": "Personal"},
        {"l": "Soll-Stunden berechnen",      "u": url("arbeitszeit:soll_stunden_berechnen"),            "g": "Personal"},
        {"l": "Organigramm",                 "u": url("hr:organigramm"),                                "g": "Personal"},
        {"l": "Stoermeldung erfassen",        "u": url("facility:erstellen"),                            "g": "Gebaeude"},
        {"l": "Meine Stoermeldungen",         "u": url("facility:meine"),                                "g": "Gebaeude"},
        {"l": "Raumuebersicht",              "u": url("raumbuch:uebersicht"),                           "g": "Gebaeude"},
        {"l": "Gebaeudeplan",                "u": url("raumbuch:grundriss"),                            "g": "Gebaeude"},
        {"l": "Buchungen",                   "u": url("raumbuch:buchung_kalender"),                     "g": "Gebaeude"},
        {"l": "Belegungsplan",               "u": url("raumbuch:belegungsplan"),                        "g": "Gebaeude"},
        {"l": "Besuchsanmeldungen",          "u": url("raumbuch:besuch_liste"),                         "g": "Gebaeude"},
        {"l": "Veranstaltungen",             "u": url("veranstaltungen:uebersicht"),                    "g": "Veranstaltungen"},
        {"l": "Meine Daten (DSGVO-Auskunft)","u": url("datenschutz:auskunft_pdf"),                     "g": "Konto"},
        {"l": "Digitale Signatur",           "u": url("signatur:dashboard"),                            "g": "Konto"},
    ]

    if hat_genehmiger:
        items.append({"l": "Genehmigungen", "u": url("formulare:genehmigung_uebersicht"), "g": "Aufgaben"})

    if ist_facility:
        items.append({"l": "Facility-Queue", "u": url("facility:queue"), "g": "Aufgaben"})

    if al_anzahl:
        items.append({"l": "Eskalationen", "u": url("facility:al_queue"), "g": "Aufgaben"})

    try:
        ma_pk = u.mitarbeiter.pk
        items.append({"l": "Meine Soll-Stunden", "u": url("arbeitszeit:mitarbeiter_soll_uebersicht", ma_pk), "g": "Personal"})
    except Exception:
        pass

    if ist_vorg:
        items.append({"l": "Team-Meldungen",       "u": url("facility:vorgesetzter"),  "g": "Gebaeude"})
        items.append({"l": "Monatsbericht Facility","u": url("facility:monatsreport"), "g": "Gebaeude"})

    if ist_facility_oder_staff:
        items.append({"l": "Wartungsplaene",      "u": url("facility:wartungsplan_liste"),  "g": "Gebaeude"})
        items.append({"l": "Gebaeudestruktur",    "u": url("raumbuch:struktur"),            "g": "Gebaeude"})
        items.append({"l": "Schluesselverwaltung","u": url("raumbuch:schluessel_liste"),     "g": "Gebaeude"})
        items.append({"l": "Zutrittsgutschriften","u": url("raumbuch:token_liste"),          "g": "Gebaeude"})
        items.append({"l": "Treppenhaeuser",      "u": url("raumbuch:treppenhaus_liste"),   "g": "Gebaeude"})
        items.append({"l": "Reinigung",           "u": url("raumbuch:reinigung"),           "g": "Gebaeude"})
        items.append({"l": "Umzugsauftraege",     "u": url("raumbuch:umzug_liste"),         "g": "Gebaeude"})

    if ist_fk:
        items.append({"l": "Token beantragen", "u": url("raumbuch:token_anfrage"), "g": "Gebaeude"})

    if hat_schicht:
        items.append({"l": "Schichtplanung",       "u": url("schichtplan:dashboard"),                    "g": "Planung"})
        items.append({"l": "Urlaubsgenehmigungen", "u": url("schichtplan:genehmigungen_uebersicht"),     "g": "Planung"})

    if u.is_staff:
        items += [
            {"l": "Rechtevergabe",          "u": url("berechtigungen:uebersicht"),          "g": "Admin"},
            {"l": "Workflow-Editor",         "u": url("workflow:workflow_editor"),            "g": "Admin"},
            {"l": "Textbausteine",           "u": url("facility:textbaustein_liste"),         "g": "Admin"},
            {"l": "Trend-Einstellungen",     "u": url("facility:einstellungen"),              "g": "Admin"},
            {"l": "Audit-Trail",             "u": url("raumbuch:gesamtlog"),                  "g": "Admin"},
            {"l": "Digitale Signatur",       "u": url("signatur:dashboard"),                  "g": "Admin"},
            {"l": "Signatur-Dokumentation",  "u": url("signatur:dokumentation_pdf"),          "g": "Admin"},
            {"l": "Datenschutz DSGVO",       "u": url("datenschutz:dashboard"),               "g": "Admin"},
        ]

    return {"cmd_items_json": items}


def hilfe_kontext(request):
    """Stellt die App-Liste und externe Dienst-URLs fuer das Hilfe-Modal bereit."""
    from django.conf import settings
    return {
        "apps_liste": [
            "arbeitszeit", "formulare", "schichtplan", "hr", "workflow",
            "facility", "raumbuch", "signatur", "datenschutz", "dokumente",
            "berechtigungen", "veranstaltungen",
        ],
        "bentopdf_url": getattr(settings, "BENTOPDF_URL", ""),
    }
