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


def prozessverantwortlicher(request):
    """Prueft ob der eingeloggte User in der Gruppe 'Prozessverantwortliche' ist.

    Gibt 'ist_prozessverantwortlicher' ans Template weiter – steuert Sichtbarkeit
    des Workflow-Editors und der Prozesszentrale-Verwaltungsfunktionen.
    Superuser und Staff haben automatisch diesen Zugang.
    """
    if not request.user.is_authenticated:
        return {"ist_prozessverantwortlicher": False}

    if request.user.is_superuser or request.user.is_staff:
        return {"ist_prozessverantwortlicher": True}

    try:
        ist_mitglied = request.user.groups.filter(
            name="Prozessverantwortliche"
        ).exists()
    except Exception:
        ist_mitglied = False

    return {"ist_prozessverantwortlicher": ist_mitglied}


def cmd_items(request):
    """Baut die Schnellsuche-Eintraege fuer die Navbar-Befehlspalette.

    Gibt 'cmd_items_json' (Python-Liste) ans Template weiter.
    Das Template rendert sie per {{ cmd_items_json|json_script:"cmd-items-data" }}
    als CSP-sicheres JSON-Datentag.
    """
    if not request.user.is_authenticated:
        return {"cmd_items_json": []}

    u = request.user

    from django.conf import settings

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
    ist_security = getattr(request, "ist_security_zugang", False)
    ist_arbeitsschutz = getattr(request, "ist_arbeitsschutz", False)
    ist_eh_verantwortlicher = getattr(request, "ist_eh_verantwortlicher", False)
    ist_eh_ersthelfer = getattr(request, "ist_eh_ersthelfer", False)
    ist_prozess = getattr(request, "ist_prozessverantwortlicher", False)
    ist_pg = getattr(request, "ist_pg_mitglied", False)
    ist_dms_admin = getattr(request, "ist_dms_admin", False)
    stellenportal_verwalten = getattr(request, "stellenportal_kann_verwalten", False)
    matrix_konfiguriert = getattr(request, "matrix_konfiguriert", False)

    items = [
        # --- Allgemein ---
        {"l": "Dashboard",                   "u": url("arbeitszeit:dashboard"),                      "g": "Allgemein"},
        {"l": "IT-Systemstatus",             "u": url("it_status:uebersicht"),                       "g": "Allgemein"},

        # --- Aufgaben ---
        {"l": "Arbeitsstapel",               "u": url("workflow:arbeitsstapel"),                     "g": "Aufgaben"},
        {"l": "Team-Stapel",                 "u": url("formulare:team_queue"),                       "g": "Aufgaben"},

        # --- Antraege ---
        {"l": "Antraege / Neuer Antrag",     "u": url("formulare:dashboard"),                        "g": "Antraege"},

        # --- Personal ---
        {"l": "Soll-Stunden Monat",          "u": url("arbeitszeit:soll_stunden_dashboard"),         "g": "Personal"},
        {"l": "Soll-Stunden Jahr",           "u": url("arbeitszeit:soll_stunden_jahresuebersicht"),  "g": "Personal"},
        {"l": "Soll-Stunden berechnen",      "u": url("arbeitszeit:soll_stunden_berechnen"),         "g": "Personal"},
        {"l": "Organigramm",                 "u": url("hr:organigramm"),                             "g": "Personal"},
        {"l": "Stellenangebote",             "u": url("stellenportal:liste"),                        "g": "Personal"},
        {"l": "Meine Bewerbungen",           "u": url("stellenportal:meine_bewerbungen"),            "g": "Personal"},

        # --- Gebaeude ---
        {"l": "Stoermeldung erfassen",       "u": url("facility:erstellen"),                         "g": "Gebaeude"},
        {"l": "Meine Stoermeldungen",        "u": url("facility:meine"),                             "g": "Gebaeude"},
        {"l": "Raumuebersicht",             "u": url("raumbuch:uebersicht"),                        "g": "Gebaeude"},
        {"l": "Gebaeudeplan",               "u": url("raumbuch:grundriss"),                         "g": "Gebaeude"},
        {"l": "Buchungen",                   "u": url("raumbuch:buchung_kalender"),                  "g": "Gebaeude"},
        {"l": "Belegungsplan",               "u": url("raumbuch:belegungsplan"),                     "g": "Gebaeude"},
        {"l": "Besuchsanmeldungen",          "u": url("raumbuch:besuch_liste"),                      "g": "Gebaeude"},

        # --- Kommunikation ---
        {"l": "Matrix-Raeume",              "u": url("matrix_integration:raum_liste"),              "g": "Kommunikation"},
        {"l": "Sitzungs-Kalender",           "u": url("matrix_integration:sitzung_liste"),           "g": "Kommunikation"},
        {"l": "Jitsi-Raeume",               "u": url("matrix_integration:jitsi_liste"),             "g": "Kommunikation"},

        # --- Veranstaltungen ---
        {"l": "Veranstaltungen",             "u": url("veranstaltungen:uebersicht"),                 "g": "Veranstaltungen"},
        {"l": "Betriebssport",               "u": url("betriebssport:uebersicht"),                   "g": "Veranstaltungen"},

        # --- Dokumente ---
        {"l": "DMS – Dokumente",             "u": url("dms:liste"),                                  "g": "Dokumente"},
        {"l": "DMS – Meine Ablage",          "u": url("dms:meine_ablage"),                           "g": "Dokumente"},
        {"l": "Meine Dokumente",             "u": url("dokumente:liste"),                            "g": "Dokumente"},

        # --- Konto ---
        {"l": "Meine Daten (DSGVO-Auskunft)","u": url("datenschutz:auskunft_pdf"),                  "g": "Konto"},
        {"l": "Digitale Signatur",           "u": url("signatur:dashboard"),                         "g": "Konto"},
    ]

    # BentoPDF
    bentopdf_url = getattr(settings, "BENTOPDF_URL", "")
    if bentopdf_url:
        items.append({"l": "PDF-Werkzeuge (BentoPDF)", "u": bentopdf_url, "g": "Dienste"})

    # OnlyOffice
    if getattr(settings, "ONLYOFFICE_URL", ""):
        items.append({"l": "Neues Dokument (OnlyOffice)",          "u": url("dms:neu"),        "g": "Dokumente"})
        items.append({"l": "Neue Tabellenkalkulation (OnlyOffice)", "u": url("dms:neu") + "?typ=xlsx", "g": "Dokumente"})
        items.append({"l": "Neue Praesentation (OnlyOffice)",       "u": url("dms:neu") + "?typ=pptx", "g": "Dokumente"})
        items.append({"l": "Dokumente bearbeiten",                  "u": url("dms:liste"),              "g": "Dokumente"})

    # Korrespondenz
    items.append({"l": "Korrespondenz (DIN 5008)", "u": url("korrespondenz:brief_liste"), "g": "Dokumente"})

    # Genehmigungen
    if hat_genehmiger:
        items.append({"l": "Genehmigungen", "u": url("formulare:genehmigung_uebersicht"), "g": "Aufgaben"})

    # Facility-Aufgaben
    if ist_facility:
        items.append({"l": "Facility-Queue", "u": url("facility:queue"), "g": "Aufgaben"})

    if al_anzahl:
        items.append({"l": "Eskalationen", "u": url("facility:al_queue"), "g": "Aufgaben"})

    # Meine Soll-Stunden
    try:
        ma_pk = u.mitarbeiter.pk
        items.append({"l": "Meine Soll-Stunden", "u": url("arbeitszeit:mitarbeiter_soll_uebersicht", ma_pk), "g": "Personal"})
    except Exception:
        pass

    # Vorgesetzten-Bereich
    if ist_vorg:
        items.append({"l": "Team-Meldungen",        "u": url("facility:vorgesetzter"),  "g": "Gebaeude"})
        items.append({"l": "Monatsbericht Facility", "u": url("facility:monatsreport"), "g": "Gebaeude"})

    # Facility / Staff
    if ist_facility_oder_staff:
        items.append({"l": "Wartungsplaene",       "u": url("facility:wartungsplan_liste"),  "g": "Gebaeude"})
        items.append({"l": "Gebaeudestruktur",     "u": url("raumbuch:struktur"),            "g": "Gebaeude"})
        items.append({"l": "Schluesselverwaltung", "u": url("raumbuch:schluessel_liste"),    "g": "Gebaeude"})
        items.append({"l": "Zutrittsgutschriften", "u": url("raumbuch:token_liste"),         "g": "Gebaeude"})
        items.append({"l": "Treppenhaeuser",       "u": url("raumbuch:treppenhaus_liste"),  "g": "Gebaeude"})
        items.append({"l": "Reinigung",            "u": url("raumbuch:reinigung"),           "g": "Gebaeude"})
        items.append({"l": "Umzugsauftraege",      "u": url("raumbuch:umzug_liste"),         "g": "Gebaeude"})

    if ist_fk:
        items.append({"l": "Token beantragen", "u": url("raumbuch:token_anfrage"), "g": "Gebaeude"})

    # Schichtplan
    if hat_schicht:
        items.append({"l": "Schichtplanung",       "u": url("schichtplan:dashboard"),                "g": "Planung"})
        items.append({"l": "Urlaubsgenehmigungen", "u": url("schichtplan:genehmigungen_uebersicht"), "g": "Planung"})

    # Sicherheit
    if ist_security:
        items.append({"l": "Sicherheits-Dashboard", "u": url("sicherheit:sicherheit_dashboard"), "g": "Sicherheit"})
        items.append({"l": "Sicherheitsalarme",      "u": url("sicherheit:alarm_liste"),          "g": "Sicherheit"})
        items.append({"l": "Brandalarme",            "u": url("sicherheit:brand_liste"),           "g": "Sicherheit"})

    if ist_arbeitsschutz:
        items.append({"l": "Arbeitsschutz – Rollenverwaltung", "u": url("sicherheit:arbeitsschutz_dashboard"), "g": "Sicherheit"})

    # Erste Hilfe
    if ist_eh_verantwortlicher:
        items.append({"l": "Erste-Hilfe – Vorfaelle",    "u": url("ersthelfe:vorfall_liste"),          "g": "Sicherheit"})
        items.append({"l": "Erste-Hilfe – Arbeitsschutz","u": url("ersthelfe:arbeitsschutz_uebersicht"),"g": "Sicherheit"})
    elif ist_eh_ersthelfer:
        items.append({"l": "Erste-Hilfe – Einsatz", "u": url("ersthelfe:arbeitsschutz_uebersicht"), "g": "Sicherheit"})

    # Prozesse / Workflow
    if ist_prozess:
        items.append({"l": "Prozesszentrale",   "u": url("workflow:prozesszentrale"),    "g": "Prozesse"})
        items.append({"l": "Workflow-Editor",   "u": url("workflow:workflow_editor"),    "g": "Prozesse"})
        items.append({"l": "Trigger-Uebersicht","u": url("workflow:trigger_uebersicht"), "g": "Prozesse"})

    # Personalgewinnung
    if ist_pg:
        items.append({"l": "Bewerbungseingang (extern)", "u": url("bewerbung:hr_liste"),             "g": "Personal"})
        items.append({"l": "Einladungscodes",             "u": url("bewerbung:hr_einladungscodes"),   "g": "Personal"})

    # Stellenportal verwalten
    if stellenportal_verwalten:
        items.append({"l": "Stellenportal verwalten", "u": url("stellenportal:hr_dashboard"), "g": "Personal"})

    # DMS-Admin
    if ist_dms_admin:
        items.append({"l": "DMS – Zugriffsantraege", "u": url("dms:zugriffsantraege"), "g": "Dokumente"})

    # Admin (Staff)
    if u.is_staff:
        items += [
            {"l": "Rechtevergabe",           "u": url("berechtigungen:uebersicht"),        "g": "Admin"},
            {"l": "Textbausteine",           "u": url("facility:textbaustein_liste"),       "g": "Admin"},
            {"l": "Trend-Einstellungen",     "u": url("facility:einstellungen"),            "g": "Admin"},
            {"l": "Audit-Trail",             "u": url("raumbuch:gesamtlog"),                "g": "Admin"},
            {"l": "Signatur-Dokumentation",  "u": url("signatur:dokumentation_pdf"),        "g": "Admin"},
            {"l": "Datenschutz DSGVO",       "u": url("datenschutz:dashboard"),             "g": "Admin"},
            {"l": "DMS – Workflow-Regeln",   "u": url("dms:workflow_regeln"),               "g": "Admin"},
            {"l": "Sensible Dokumente",      "u": url("dokumente:liste"),                   "g": "Admin"},
            {"l": "Matrix-Templates",        "u": url("matrix_integration:template_liste"), "g": "Admin"},
        ]

    return {"cmd_items_json": items}


def personalgewinnung_kontext(request):
    """Prueft ob der User im PG-Team (Personalgewinnung) ist."""
    if not request.user.is_authenticated:
        return {"ist_pg_mitglied": False}
    try:
        from formulare.models import TeamQueue
        ist_pg = TeamQueue.objects.filter(kuerzel="PG", mitglieder=request.user).exists()
    except Exception:
        ist_pg = False
    return {"ist_pg_mitglied": ist_pg}


def dms_badge_kontext(request):
    """Zaehlt offene DMS-Zugriffsantraege fuer DMS-Admins und Dokumenten-Ersteller.

    Gibt 'dms_zugriffsantraege_anzahl' ans Template weiter – wird in der Navbar
    als Badge am DMS-Link angezeigt.
    """
    if not request.user.is_authenticated:
        return {"dms_zugriffsantraege_anzahl": 0}

    try:
        from dms.models import DokumentZugriffsschluessel, Dokument
        from django.db.models import Q

        from formulare.models import TeamQueue as _TQ
        ist_dms_admin = (
            request.user.is_superuser
            or request.user.is_staff
            or request.user.groups.filter(name="DMS-Admin").exists()
            or _TQ.objects.filter(kuerzel="dms", mitglieder=request.user).exists()
        )

        if ist_dms_admin:
            # DMS-Admin sieht alle offenen Antraege
            anzahl = DokumentZugriffsschluessel.objects.filter(
                status=DokumentZugriffsschluessel.STATUS_OFFEN
            ).count()
        else:
            # Dokumenten-Ersteller sieht nur Antraege auf eigene Dokumente
            eigene_dok_ids = Dokument.objects.filter(
                erstellt_von=request.user
            ).values_list("id", flat=True)
            anzahl = DokumentZugriffsschluessel.objects.filter(
                status=DokumentZugriffsschluessel.STATUS_OFFEN,
                dokument_id__in=eigene_dok_ids,
            ).count()
    except Exception:
        anzahl = 0

    return {
        "dms_zugriffsantraege_anzahl": anzahl,
        "ist_dms_admin": ist_dms_admin,
    }


def hilfe_kontext(request):
    """Stellt die App-Liste und externe Dienst-URLs fuer das Hilfe-Modal bereit."""
    from django.conf import settings
    return {
        "apps_liste": [
            "arbeitszeit", "formulare", "schichtplan", "hr", "workflow",
            "facility", "raumbuch", "signatur", "datenschutz", "dokumente",
            "dms", "berechtigungen", "veranstaltungen", "bewerbung",
            "stellenportal", "betriebssport",
        ],
        "bentopdf_url": getattr(settings, "BENTOPDF_URL", ""),
        "onlyoffice_url": getattr(settings, "ONLYOFFICE_URL", ""),
    }
