"""Workflow-Engine: Zentrale Logik fuer Workflow-Verwaltung

Phase 1 (MVP):
- start_workflow(): Workflow aus Template starten
- resolve_rolle(): Zustaendigkeiten aufloesen
- create_tasks(): Tasks erstellen
- complete_task(): Naechsten Schritt aktivieren

Phase 2 (Graph-Workflows):
- get_next_steps_via_transitions(): Graph-basierte Navigation
- execute_auto_action(): Automatische Aktionen
- Erweiterte complete_task(): Graph vs. Linear
"""
from datetime import timedelta
import logging
import uuid

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from .models import WorkflowInstance, WorkflowStep, WorkflowTask, WorkflowTransition

logger = logging.getLogger(__name__)

User = get_user_model()


class WorkflowEngine:
    """Zentrale Workflow-Engine."""

    def start_workflow(self, template, content_object, user):
        """Startet einen neuen Workflow aus einem Template.

        Args:
            template: WorkflowTemplate Instanz
            content_object: Verknuepftes Objekt (z.B. ZAGAntrag)
            user: User der den Workflow startet

        Returns:
            WorkflowInstance

        Beispiel:
            engine = WorkflowEngine()
            instance = engine.start_workflow(template, zag_antrag, request.user)
        """
        with transaction.atomic():
            # WorkflowInstance erstellen
            content_type = ContentType.objects.get_for_model(content_object)
            instance = WorkflowInstance.objects.create(
                template=template,
                content_type=content_type,
                object_id=content_object.pk,
                status="laufend",
                gestartet_von=user,
                fortschritt=0,
            )

            # Ersten Schritt(e) erstellen
            erste_schritte = template.schritte.filter(reihenfolge=1)
            for schritt in erste_schritte:
                self.create_tasks_for_step(instance, schritt, content_object)

            # Ersten Schritt als aktuellen Schritt setzen
            if erste_schritte.exists():
                instance.aktueller_schritt = erste_schritte.first()
                instance.save()

            # Fortschritt berechnen
            instance.update_fortschritt()

            return instance

    def resolve_rolle(self, rolle, antragsteller_stelle=None, org_einheit=None):
        """Loest eine Rolle zu einer konkreten Stelle auf.

        Args:
            rolle: Rollen-String (z.B. "direkte_fuehrungskraft")
            antragsteller_stelle: Stelle des Antragstellers (hr.Stelle)
            org_einheit: OrgEinheit falls relevant (hr.OrgEinheit)

        Returns:
            hr.Stelle Instanz oder None

        Beispiel:
            stelle = engine.resolve_rolle("direkte_fuehrungskraft", antragsteller.stelle)
        """
        from hr.models import Stelle, OrgEinheit

        # Feste Rollen
        if rolle == "hr":
            return Stelle.objects.filter(kuerzel__istartswith="hr").first()

        if rolle == "gf":
            return Stelle.objects.filter(kuerzel__istartswith="gf").first()

        # Antragsteller
        if rolle == "antragsteller":
            return antragsteller_stelle

        # Hierarchie-basierte Rollen
        if not antragsteller_stelle:
            return None

        if rolle in ("direkte_fuehrungskraft", "direkter_vorgesetzter"):
            return self._find_uebergeordnete_stelle(antragsteller_stelle)

        if rolle in ("abteilungsleitung", "bereichsleiter"):
            return self._find_abteilungsleitung(antragsteller_stelle)

        if rolle == "bereichsleitung":
            return self._find_bereichsleitung(antragsteller_stelle)

        # Fallback: None
        return None

    def create_tasks_for_step(self, instance, step, content_object=None):
        """Erstellt Tasks fuer einen WorkflowStep.

        Args:
            instance: WorkflowInstance
            step: WorkflowStep
            content_object: Verknuepftes Objekt (optional, fuer Zustaendigkeitsaufloesung)

        Returns:
            Liste von WorkflowTask Instanzen

        Beispiel:
            tasks = engine.create_tasks_for_step(instance, step, zag_antrag)
        """
        # Pruefe bedingte Aktivierung (z.B. GF-Freigabe nur bei hohen Kosten)
        if not self._should_activate_step(step, content_object):
            return []  # Schritt ueberspringen

        # NEU: Auto-Aktionen sofort ausfuehren, keinen Task erstellen
        if step.schritt_typ == "auto":
            self.execute_auto_action(step, instance, content_object)

            # Sofort weiter zu naechsten Schritten
            if instance.template.ist_graph_workflow:
                # Fake-Task fuer Transition-Evaluierung
                fake_task_class = type('FakeTask', (object,), {
                    'step': step,
                    'instance': instance,
                    'entscheidung': 'auto_completed'
                })
                fake_task = fake_task_class()
                naechste_schritte = self.get_next_steps_via_transitions(fake_task, content_object)
                for next_step in naechste_schritte:
                    self.create_tasks_for_step(instance, next_step, content_object)
            return []

        # Frist berechnen
        frist = timezone.now() + timedelta(days=step.frist_tage)

        # Team-Queue Zuweisung
        if step.zustaendig_rolle == "team_queue" and step.zustaendig_team:
            # Task an Team-Queue zuweisen
            task = WorkflowTask.objects.create(
                instance=instance,
                step=step,
                zugewiesen_an_team=step.zustaendig_team,
                status="offen",
                frist=frist,
            )
            return [task]

        # Stellen-basierte Zuweisung (bestehende Logik)
        # Antragsteller-Stelle ermitteln
        antragsteller_stelle = None
        if content_object:
            # Versuche verschiedene Attributnamen
            ma = None
            if hasattr(content_object, "antragsteller"):
                ma = content_object.antragsteller
            elif hasattr(content_object, "mitarbeiter"):
                ma = content_object.mitarbeiter

            # Hole Stelle vom Mitarbeiter
            if ma and hasattr(ma, "user") and hasattr(ma.user, "hr_mitarbeiter"):
                antragsteller_stelle = ma.user.hr_mitarbeiter.stelle

        # Zustaendigkeit aufloesen
        if step.zustaendig_stelle:
            # Feste Stelle im Schritt definiert
            zustaendige_stelle = step.zustaendig_stelle
        elif step.zustaendig_rolle:
            # Rolle aufloesen
            zustaendige_stelle = self.resolve_rolle(
                step.zustaendig_rolle,
                antragsteller_stelle=antragsteller_stelle,
                org_einheit=step.zustaendig_org,
            )
        else:
            # Keine Zustaendigkeit definiert → Fallback an GF
            zustaendige_stelle = self.resolve_rolle("gf")

        # Fallback wenn Stelle nicht gefunden
        if not zustaendige_stelle:
            zustaendige_stelle = self.resolve_rolle("gf")

        # Task erstellen
        task = WorkflowTask.objects.create(
            instance=instance,
            step=step,
            zugewiesen_an_stelle=zustaendige_stelle,
            status="offen",
            frist=frist,
        )

        return [task]

    def get_next_steps_via_transitions(self, task, content_object):
        """Findet naechste Schritte basierend auf Transitions (Graph-Logik).

        Args:
            task: WorkflowTask Instanz (abgeschlossener Task)
            content_object: Verknuepftes Objekt (z.B. ZAGAntrag)

        Returns:
            List[WorkflowStep]: Liste der naechsten Schritte (kann leer, 1 oder mehrere sein)

        Beispiel:
            naechste = engine.get_next_steps_via_transitions(task, zag_antrag)
        """
        instance = task.instance
        template = instance.template

        # Hole alle Transitions die vom aktuellen Schritt ausgehen
        transitions = WorkflowTransition.objects.filter(
            template=template,
            von_schritt=task.step
        ).order_by("prioritaet")

        # Evaluiere Bedingungen
        naechste_schritte = []
        for transition in transitions:
            if transition.evaluate(task, content_object):
                if transition.zu_schritt:
                    naechste_schritte.append(transition.zu_schritt)
                else:
                    # NULL = Ende des Workflows
                    return []

        return naechste_schritte

    def execute_auto_action(self, step, instance, content_object):
        """Fuehrt automatische Aktionen aus (ohne User-Interaktion).

        Wird aufgerufen wenn schritt_typ == "auto".

        Args:
            step: WorkflowStep Instanz
            instance: WorkflowInstance
            content_object: Verknuepftes Objekt

        Beispiel:
            engine.execute_auto_action(step, instance, zag_antrag)
        """
        if step.aktion_typ == "benachrichtigen":
            self._send_notification(step, instance, content_object)

        elif step.aktion_typ == "email":
            self._send_email(step, instance, content_object)

        elif step.aktion_typ == "webhook":
            self._call_webhook(step, instance, content_object)

        elif step.aktion_typ == "python_code":
            self._execute_python_code(step, instance, content_object)

        elif step.aktion_typ == "verteilen":
            self._verteilen(step, instance, content_object)

        elif step.aktion_typ == "archivieren":
            self._archiviere_in_dms(step, instance, content_object)

        elif step.aktion_typ == "loeschung_freigeben":
            self._loeschfreigabe_setzen(step, instance, content_object)

    def _archiviere_in_dms(self, step, instance, content_object):
        """Archiviert das verknuepfte Objekt in der angegebenen DMS-Kategorie.

        Erwartet in step.auto_config: {"kategorie_id": <int>}

        Unterstuetzte content_object-Typen:
          - dms.Dokument        → Kategorie des bestehenden Dokuments aendern
          - alle anderen        → archiviere_in_dms(kategorie_id)-Methode aufrufen
        """
        config = step.auto_config or {}
        kategorie_id = config.get("kategorie_id")
        if not kategorie_id:
            logger.warning(
                "archivieren-Schritt %s hat keine kategorie_id in auto_config", step.pk
            )
            return
        try:
            if hasattr(content_object, "archiviere_in_dms"):
                content_object.archiviere_in_dms(kategorie_id)
                logger.info(
                    "DMS-Archivierung OK: %s pk=%s -> Kategorie %s",
                    type(content_object).__name__, content_object.pk, kategorie_id,
                )
            else:
                logger.warning(
                    "DMS-Archivierung: %s hat keine archiviere_in_dms-Methode",
                    type(content_object).__name__,
                )
        except Exception as exc:
            logger.error(
                "DMS-Archivierung fehlgeschlagen fuer %s pk=%s: %s",
                type(content_object).__name__, content_object.pk, exc,
            )

    def _loeschfreigabe_setzen(self, step, instance, content_object):
        """Setzt das Loeschfreigabe-Flag am verknuepften DMS-Dokument.

        Wird aufgerufen wenn DSB-Team den Loeschantrag genehmigt hat.
        Erwartet content_object mit loeschfreigabe_setzen()-Methode (dms.Dokument).
        """
        try:
            if hasattr(content_object, "loeschfreigabe_setzen"):
                content_object.loeschfreigabe_setzen()
                logger.info(
                    "Loeschfreigabe gesetzt: %s pk=%s",
                    type(content_object).__name__, content_object.pk,
                )
            else:
                logger.warning(
                    "Loeschfreigabe: %s hat keine loeschfreigabe_setzen-Methode",
                    type(content_object).__name__,
                )
        except Exception as exc:
            logger.error(
                "Loeschfreigabe fehlgeschlagen fuer %s pk=%s: %s",
                type(content_object).__name__, content_object.pk, exc,
            )

    def _send_notification(self, step, instance, content_object):
        """Sendet Benachrichtigung an User/Team.

        Args:
            step: WorkflowStep mit auto_config
            instance: WorkflowInstance
            content_object: Verknuepftes Objekt
        """
        config = step.auto_config or {}
        nachricht = config.get("nachricht", "Workflow-Benachrichtigung")
        user_ids = config.get("user_ids", [])

        logger.info(
            f"Benachrichtigung gesendet: {nachricht} an User-IDs: {user_ids}"
        )

        # TODO: Integration mit Notification-System
        # from django.contrib.auth import get_user_model
        # User = get_user_model()
        # for user_id in user_ids:
        #     user = User.objects.get(id=user_id)
        #     # Notification erstellen...

    def _send_email(self, step, instance, content_object):
        """Sendet Email.

        Args:
            step: WorkflowStep mit auto_config
            instance: WorkflowInstance
            content_object: Verknuepftes Objekt
        """
        config = step.auto_config or {}
        betreff = config.get("betreff", "Workflow-Benachrichtigung")
        text = config.get("text", "")
        empfaenger = config.get("empfaenger", "")

        from django.core.mail import send_mail
        try:
            send_mail(
                subject=betreff,
                message=text,
                from_email="noreply@firma.de",
                recipient_list=[empfaenger],
                fail_silently=False,
            )
            logger.info(f"Email gesendet an {empfaenger}: {betreff}")
        except Exception as e:
            logger.error(f"Email-Versand fehlgeschlagen: {e}")

    def _call_webhook(self, step, instance, content_object):
        """Ruft Webhook auf.

        Args:
            step: WorkflowStep mit auto_config
            instance: WorkflowInstance
            content_object: Verknuepftes Objekt
        """
        import requests
        config = step.auto_config or {}
        url = config.get("url", "")
        method = config.get("method", "POST")
        data = config.get("data", {})

        try:
            if method == "POST":
                response = requests.post(url, json=data, timeout=10)
                logger.info(f"Webhook POST erfolgreich: {url} - Status: {response.status_code}")
            elif method == "GET":
                response = requests.get(url, params=data, timeout=10)
                logger.info(f"Webhook GET erfolgreich: {url} - Status: {response.status_code}")
        except Exception as e:
            logger.error(f"Webhook-Aufruf fehlgeschlagen: {e}")

    def _execute_python_code(self, step, instance, content_object):
        """Fuehrt Python-Code aus (VORSICHT: Sicherheitsrisiko!).

        Args:
            step: WorkflowStep mit auto_config
            instance: WorkflowInstance
            content_object: Verknuepftes Objekt
        """
        config = step.auto_config or {}
        code = config.get("code", "")

        try:
            local_vars = {
                "instance": instance,
                "content_object": content_object,
                "step": step,
            }
            exec(code, {}, local_vars)
            logger.info(f"Python-Code erfolgreich ausgefuehrt fuer Schritt: {step.titel}")
        except Exception as e:
            logger.error(f"Python-Code-Ausfuehrung fehlgeschlagen: {e}")

    def complete_task(self, task, entscheidung, kommentar, user, ziel_user=None):
        """Erledigt einen Task und aktiviert naechste Schritte.

        Args:
            task: WorkflowTask Instanz
            entscheidung: "genehmigt", "abgelehnt", etc.
            kommentar: Kommentar-Text
            user: User der die Entscheidung trifft
            ziel_user: Optional - Ziel-User bei Weiterleitung

        Returns:
            Liste der neu erstellten Tasks

        Beispiel:
            neue_tasks = engine.complete_task(task, "genehmigt", "OK", request.user)
        """
        with transaction.atomic():
            # Task als erledigt markieren
            task.entscheidung = entscheidung
            task.kommentar = kommentar
            task.erledigt_am = timezone.now()
            task.erledigt_von = user
            task.status = "erledigt"
            task.save()

            # Fortschritt aktualisieren
            task.instance.update_fortschritt()

            neue_tasks = []

            # Sonderfaelle: Weiterleitung und Ruecksendung
            if entscheidung == "weitergeleitet" and ziel_user:
                # Task an andere Person weiterleiten (gleicher Schritt, neue Zuweisung)
                neuer_task = WorkflowTask.objects.create(
                    instance=task.instance,
                    step=task.step,
                    zugewiesen_an_user=ziel_user,
                    frist=timezone.now() + timedelta(days=task.step.frist_tage),
                    status="offen",
                )
                return [neuer_task]

            if entscheidung == "zurueck_genehmiger":
                # Finde vorherigen Genehmiger (letzter Task mit entscheidung='genehmigt')
                vorheriger_task = (
                    task.instance.tasks.filter(
                        entscheidung="genehmigt",
                        status="erledigt"
                    )
                    .order_by("-erledigt_am")
                    .first()
                )
                if vorheriger_task and vorheriger_task.erledigt_von:
                    neuer_task = WorkflowTask.objects.create(
                        instance=task.instance,
                        step=task.step,
                        zugewiesen_an_user=vorheriger_task.erledigt_von,
                        frist=timezone.now() + timedelta(days=task.step.frist_tage),
                        status="offen",
                    )
                    return [neuer_task]
                # Falls kein Genehmiger gefunden → normaler Workflow

            if entscheidung == "zurueck_antragsteller":
                # Zurueck an Person die Workflow gestartet hat
                if task.instance.gestartet_von:
                    neuer_task = WorkflowTask.objects.create(
                        instance=task.instance,
                        step=task.step,
                        zugewiesen_an_user=task.instance.gestartet_von,
                        frist=timezone.now() + timedelta(days=task.step.frist_tage),
                        status="offen",
                    )
                    return [neuer_task]
                # Falls kein Starter gefunden → normaler Workflow

            # Bei Genehmigung: bearbeitet_von / bearbeitet_am am Antrag setzen
            # (nur beim ersten genehmigenden Schritt, falls noch leer)
            if entscheidung == "genehmigt":
                co = task.instance.content_object
                if co is not None:
                    felder_bearbeitung = []
                    if hasattr(co, "bearbeitet_von") and co.bearbeitet_von is None:
                        co.bearbeitet_von = user
                        felder_bearbeitung.append("bearbeitet_von")
                    if hasattr(co, "bearbeitet_am") and co.bearbeitet_am is None:
                        co.bearbeitet_am = timezone.now()
                        felder_bearbeitung.append("bearbeitet_am")
                    if felder_bearbeitung:
                        co.save(update_fields=felder_bearbeitung)

            # Workflow-Logik basierend auf Entscheidung
            if entscheidung == "abgelehnt":
                # Bei Ablehnung: Workflow abbrechen und Antrag ablehnen
                task.instance.status = "abgebrochen"
                task.instance.abgeschlossen_am = timezone.now()
                task.instance.save()

                # Verknuepftes Antrag-Objekt auf "abgelehnt" setzen
                co = task.instance.content_object
                if co is not None and hasattr(co, "status"):
                    co.status = "abgelehnt"
                    co.save(update_fields=["status"])

                return []

            # === NEUE LOGIK: Graph vs. Linear ===
            instance = task.instance
            content_object = instance.content_object

            if instance.template.ist_graph_workflow:
                # Graph-basiert: Transitions bestimmen naechste Schritte (Liste, kein Retry)
                naechste_schritte = self.get_next_steps_via_transitions(task, content_object)
                for schritt in naechste_schritte:
                    neue_tasks.extend(
                        self.create_tasks_for_step(instance, schritt, content_object)
                    )
                if neue_tasks and naechste_schritte:
                    instance.aktueller_schritt = naechste_schritte[0]
                    instance.save()
            else:
                # Legacy: Linear mit Retry-Loop (ueberspringt bedingte Schritte)
                aktuelle_reihenfolge = task.step.reihenfolge
                naechste_reihenfolge = aktuelle_reihenfolge + 1
                naechste_schritte = instance.template.schritte.filter(
                    reihenfolge=naechste_reihenfolge
                )
                max_versuche = 10  # Verhindere Endlosschleife
                versuche = 0

                while naechste_schritte.exists() and not neue_tasks and versuche < max_versuche:
                    for schritt in naechste_schritte:
                        neue_tasks.extend(
                            self.create_tasks_for_step(instance, schritt, content_object)
                        )

                    if neue_tasks:
                        instance.aktueller_schritt = naechste_schritte.first()
                        instance.save()
                    else:
                        naechste_reihenfolge += 1
                        naechste_schritte = instance.template.schritte.filter(
                            reihenfolge=naechste_reihenfolge
                        )

                    versuche += 1

            # Falls keine Tasks erstellt wurden und keine weiteren Schritte → Workflow abschliessen
            hat_weitere_schritte = bool(naechste_schritte)
            if not neue_tasks and not hat_weitere_schritte:
                offene_tasks = task.instance.tasks.filter(
                    status__in=["offen", "in_bearbeitung"]
                ).count()

                if offene_tasks == 0:
                    task.instance.status = "abgeschlossen"
                    task.instance.abgeschlossen_am = timezone.now()
                    task.instance.aktueller_schritt = None
                    task.instance.save()

                    # Verknuepftes Antrag-Objekt auf "genehmigt" setzen
                    co = task.instance.content_object
                    if co is not None and hasattr(co, "status"):
                        co.status = "genehmigt"
                        felder = ["status"]

                        # Fuer Dienstreiseantraege: Einladungscode generieren
                        if hasattr(co, "einladungscode") and not co.einladungscode:
                            co.einladungscode = uuid.uuid4().hex[:8].upper()
                            felder.append("einladungscode")

                        co.save(update_fields=felder)

            return neue_tasks

    # ========================================================================
    # HELPER-METHODEN
    # ========================================================================

    def _find_uebergeordnete_stelle(self, stelle, max_ebenen=5):
        """Findet die naechste besetzte uebergeordnete Stelle.

        Args:
            stelle: Ausgangs-Stelle
            max_ebenen: Maximale Anzahl Ebenen nach oben

        Returns:
            Stelle oder None
        """
        current = stelle.uebergeordnete_stelle
        ebenen = 0

        while current and ebenen < max_ebenen:
            # Wenn Stelle besetzt ist → zurueckgeben
            if current.ist_besetzt:
                return current

            # Sonst eine Ebene hoeher
            current = current.uebergeordnete_stelle
            ebenen += 1

        # Falls nicht gefunden: letzte gefundene Stelle zurueckgeben
        # (auch wenn unbesetzt, besser als None)
        return current

    def _find_abteilungsleitung(self, stelle):
        """Findet die Abteilungsleitung fuer eine Stelle.

        Logik:
        1. Finde OrgEinheit der Stelle
        2. Wenn typ=Abteilung → finde Leitung dieser Abteilung
        3. Wenn typ=Team → gehe zur uebergeordneten Abteilung

        Args:
            stelle: Stelle des Antragstellers

        Returns:
            Stelle oder None
        """
        org = stelle.org_einheit
        if not org:
            return None

        # Wenn Stelle direkt in Abteilung → finde Leitung
        # Annahme: Leitung hat kategorie='leitung' in dieser OrgEinheit
        leitung = (
            stelle.__class__.objects.filter(
                org_einheit=org, kategorie="leitung"
            ).first()
        )

        if leitung:
            return leitung

        # Fallback: gehe zur uebergeordneten OrgEinheit
        if org.uebergeordnet:
            return self._find_abteilungsleitung_in_org(org.uebergeordnet)

        return None

    def _find_abteilungsleitung_in_org(self, org_einheit):
        """Findet Leitung in einer OrgEinheit."""
        from hr.models import Stelle

        return Stelle.objects.filter(
            org_einheit=org_einheit, kategorie="leitung"
        ).first()

    def _find_bereichsleitung(self, stelle):
        """Findet die Bereichsleitung fuer eine Stelle.

        Logik:
        1. Gehe die OrgEinheit-Hierarchie hoch bis zum Bereich
        2. Finde Leitung des Bereichs

        Args:
            stelle: Stelle des Antragstellers

        Returns:
            Stelle oder None
        """
        org = stelle.org_einheit
        if not org:
            return None

        # Gehe die Hierarchie hoch bis zum Bereich (2. Ebene nach GF)
        current_org = org
        max_ebenen = 5
        ebenen = 0

        while current_org and ebenen < max_ebenen:
            # Pruefe ob das ein Bereich ist (hat GF als uebergeordnet)
            if (
                current_org.uebergeordnet
                and current_org.uebergeordnet.kuerzel == "GF"
            ):
                # Das ist ein Bereich → finde Leitung
                return self._find_abteilungsleitung_in_org(current_org)

            current_org = current_org.uebergeordnet
            ebenen += 1

        return None

    def _interpoliere(self, text, instance, content_object):
        """Ersetzt Platzhalter in Nachrichtentext durch echte Werte.

        Verfuegbare Platzhalter:
            {{template_name}}       Name des Workflow-Templates
            {{datum}}               Heutiges Datum (TT.MM.JJJJ)
            {{antragsteller_name}}  Vollstaendiger Name des Antragstellers
            {{antragsteller_email}} E-Mail-Adresse des Antragstellers
            {{status}}              Aktueller Status des verknuepften Objekts
            {{objekt}}              String-Darstellung des verknuepften Objekts

        Args:
            text: Text mit Platzhaltern
            instance: WorkflowInstance
            content_object: Verknuepftes Objekt

        Returns:
            str: Text mit aufgeloesten Platzhaltern
        """
        # Workflow-Starter (gestartet_von)
        starter = instance.gestartet_von
        starter_name = (
            starter.get_full_name() or starter.username if starter else ""
        )

        werte = {
            "{{template_name}}": instance.template.name,
            "{{datum}}": timezone.now().strftime("%d.%m.%Y"),
            "{{uhrzeit}}": timezone.now().strftime("%H:%M"),
            "{{status}}": str(getattr(content_object, "status", "")),
            "{{objekt}}": str(content_object) if content_object else "",
            "{{user_name}}": starter_name,
            # Generische Felder die viele Content-Objects haben
            "{{titel}}": str(getattr(content_object, "titel", "")),
            "{{beschreibung}}": str(getattr(content_object, "beschreibung", "")),
            "{{system}}": str(getattr(getattr(content_object, "system", None), "__str__", lambda: "")()),
        }

        # Antragsteller ermitteln
        antragsteller = None
        if content_object:
            if hasattr(content_object, "antragsteller"):
                antragsteller = content_object.antragsteller
            elif hasattr(content_object, "erstellt_von"):
                antragsteller = content_object.erstellt_von
            elif (
                hasattr(content_object, "mitarbeiter")
                and hasattr(content_object.mitarbeiter, "user")
            ):
                antragsteller = content_object.mitarbeiter.user

        if antragsteller:
            werte["{{antragsteller_name}}"] = (
                antragsteller.get_full_name() or antragsteller.username
            )
            werte["{{antragsteller_email}}"] = antragsteller.email or ""
        else:
            werte["{{antragsteller_name}}"] = ""
            werte["{{antragsteller_email}}"] = ""

        for platzhalter, wert in werte.items():
            text = text.replace(platzhalter, wert)
        return text

    def _verteilen(self, step, instance, content_object):
        """Verteiler-Aktion: sendet Nachrichten ueber mehrere Kanaele.

        Liest auto_config["kanaele"] und ruft fuer jeden Eintrag den
        passenden Kanal-Handler auf.

        Unterstuetzte Kanaele:
            email   → Django send_mail (via Mailpit oder Stalwart)
            matrix  → Matrix-Bot (falls konfiguriert)
            intern  → Protokoll-Eintrag (kuenftig: PRIMA-Benachrichtigung)

        auto_config-Beispiel:
        {
            "kanaele": [
                {
                    "typ": "email",
                    "empfaenger": "{{antragsteller_email}}",
                    "betreff": "Prozess {{template_name}} abgeschlossen",
                    "text": "Sehr geehrte/r {{antragsteller_name}}, ..."
                },
                {
                    "typ": "matrix",
                    "nachricht": "Prozess {{template_name}} abgeschlossen."
                },
                {
                    "typ": "intern",
                    "nachricht": "Ihr Antrag wurde bearbeitet."
                }
            ]
        }
        """
        config = step.auto_config or {}
        kanaele = config.get("kanaele", [])

        for kanal in kanaele:
            typ = kanal.get("typ", "")
            try:
                if typ == "email":
                    self._verteilen_email(kanal, instance, content_object)
                elif typ == "matrix":
                    self._verteilen_matrix(kanal, instance, content_object)
                elif typ == "intern":
                    self._verteilen_intern(kanal, instance, content_object)
                else:
                    logger.warning(
                        "Unbekannter Verteiler-Kanal '%s' in Schritt %s",
                        typ, step.pk,
                    )
            except Exception as exc:
                logger.error(
                    "Verteiler-Kanal '%s' fehlgeschlagen in Schritt %s: %s",
                    typ, step.pk, exc,
                )

    def _verteilen_email(self, kanal, instance, content_object):
        """Sendet eine E-Mail ueber den konfigurierten SMTP-Server (Mailpit)."""
        from django.core.mail import send_mail
        from django.conf import settings as django_settings

        empfaenger_raw = self._interpoliere(
            kanal.get("empfaenger", ""), instance, content_object
        )
        betreff = self._interpoliere(
            kanal.get("betreff", "Workflow-Benachrichtigung"), instance, content_object
        )
        text = self._interpoliere(
            kanal.get("text", ""), instance, content_object
        )
        absender = getattr(django_settings, "DEFAULT_FROM_EMAIL", "prima@prima.intern")

        # Mehrere Empfaenger durch Komma trennen
        empfaenger_liste = [
            e.strip() for e in empfaenger_raw.split(",") if e.strip()
        ]
        if not empfaenger_liste:
            logger.warning(
                "Verteiler E-Mail: kein Empfaenger konfiguriert (Instanz %s)", instance.pk
            )
            return

        send_mail(
            subject=betreff,
            message=text,
            from_email=absender,
            recipient_list=empfaenger_liste,
            fail_silently=False,
        )
        logger.info(
            "Verteiler E-Mail gesendet an %s: %s (Instanz %s)",
            empfaenger_liste, betreff, instance.pk,
        )

    def _verteilen_matrix(self, kanal, instance, content_object):
        """Sendet eine Matrix-Nachricht (nutzt bestehende Matrix-Integration)."""
        from django.conf import settings as django_settings

        nachricht = self._interpoliere(
            kanal.get("nachricht", ""), instance, content_object
        )
        raum_id = kanal.get("raum_id", "")

        # Fallback: Room-ID aus DB holen wenn nicht im Kanal konfiguriert
        if not raum_id:
            raum_id = getattr(django_settings, "MATRIX_FACILITY_ROOM_ID", "")
        if not raum_id:
            try:
                from matrix_integration.models import MatrixRaum
                ping_raum = MatrixRaum.objects.filter(
                    ping_typ="facility", ist_aktiv=True
                ).exclude(room_id="").first()
                if ping_raum:
                    raum_id = ping_raum.room_id
            except Exception:
                pass

        if not raum_id:
            logger.warning(
                "Verteiler Matrix: kein Raum konfiguriert (Instanz %s)", instance.pk
            )
            return

        bot_token = getattr(django_settings, "MATRIX_BOT_TOKEN", "")
        homeserver = getattr(django_settings, "MATRIX_HOMESERVER_INTERNAL_URL", "") or getattr(django_settings, "MATRIX_HOMESERVER_URL", "")
        if not bot_token or not homeserver:
            logger.warning(
                "Verteiler Matrix: MATRIX_BOT_TOKEN oder MATRIX_HOMESERVER_URL fehlen"
            )
            return

        import time
        import urllib.request
        import json as jsonlib

        txn_id = str(int(time.time() * 1000))
        url = f"{homeserver}/_matrix/client/v3/rooms/{raum_id}/send/m.room.message/{txn_id}"
        payload = jsonlib.dumps({"msgtype": "m.text", "body": nachricht}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {bot_token}",
                "Content-Type": "application/json",
            },
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
        logger.info(
            "Verteiler Matrix-Nachricht gesendet an %s (Instanz %s)", raum_id, instance.pk
        )

    def _verteilen_intern(self, kanal, instance, content_object):
        """Interne PRIMA-Benachrichtigung – wird als Protokoll-Eintrag geloggt.

        Kuenftige Erweiterung: dediziertes Benachrichtigungsmodell oder
        WorkflowTask mit status='erledigt' fuer den Antragsteller.
        """
        nachricht = self._interpoliere(
            kanal.get("nachricht", ""), instance, content_object
        )
        logger.info(
            "Verteiler Intern: '%s' (Instanz %s, Template '%s')",
            nachricht, instance.pk, instance.template.name,
        )

    def _should_activate_step(self, step, content_object):
        """Prueft ob ein Workflow-Schritt aktiviert werden soll.

        Verwendet Settings-basierte Regeln fuer bedingte Schritte.

        Args:
            step: WorkflowStep Instanz
            content_object: Verknuepftes Objekt (z.B. Dienstreiseantrag)

        Returns:
            bool: True wenn Schritt aktiviert werden soll, False zum Ueberspringen
        """
        from django.conf import settings

        # Regel: GF-Freigabe bei Dienstreisen nur bei hohen Kosten
        if step.zustaendig_rolle == "gf" and content_object:
            # Pruefe ob es ein Dienstreiseantrag ist
            if hasattr(content_object, 'geschaetzte_kosten'):
                schwelle = getattr(settings, 'DIENSTREISE_GF_FREIGABE_SCHWELLE', 1000)
                if content_object.geschaetzte_kosten < schwelle:
                    # Kosten unter Schwelle → Schritt ueberspringen
                    return False

        # Standardmaessig: Schritt aktivieren
        return True
