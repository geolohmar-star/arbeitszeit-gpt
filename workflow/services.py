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

        if rolle == "direkte_fuehrungskraft":
            return self._find_uebergeordnete_stelle(antragsteller_stelle)

        if rolle == "abteilungsleitung":
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

            # Workflow-Logik basierend auf Entscheidung
            if entscheidung == "abgelehnt":
                # Bei Ablehnung: Workflow abbrechen
                task.instance.status = "abgebrochen"
                task.instance.abgeschlossen_am = timezone.now()
                task.instance.save()
                return []

            # === NEUE LOGIK: Graph vs. Linear ===
            instance = task.instance
            content_object = instance.content_object

            if instance.template.ist_graph_workflow:
                # Graph-basiert: Transitions evaluieren
                naechste_schritte = self.get_next_steps_via_transitions(task, content_object)
            else:
                # Legacy: Linear mit reihenfolge
                aktuelle_reihenfolge = task.step.reihenfolge
                naechste_reihenfolge = aktuelle_reihenfolge + 1
                naechste_schritte = instance.template.schritte.filter(
                    reihenfolge=naechste_reihenfolge
                )

            # Versuche naechste Schritte zu aktivieren (mit Skip-Logik)
            max_versuche = 10  # Verhindere Endlosschleife
            versuche = 0

            while naechste_schritte.exists() and not neue_tasks and versuche < max_versuche:
                # Versuche Tasks fuer naechste Schritte zu erstellen
                for schritt in naechste_schritte:
                    neue_tasks.extend(
                        self.create_tasks_for_step(
                            task.instance, schritt, task.instance.content_object
                        )
                    )

                if neue_tasks:
                    # Tasks erfolgreich erstellt → aktuellen Schritt aktualisieren
                    task.instance.aktueller_schritt = naechste_schritte.first()
                    task.instance.save()
                else:
                    # Keine Tasks erstellt (Schritt uebersprungen) → naechsten Schritt versuchen
                    naechste_reihenfolge += 1
                    naechste_schritte = task.instance.template.schritte.filter(
                        reihenfolge=naechste_reihenfolge
                    )

                versuche += 1

            # Falls keine Tasks erstellt wurden und auch keine weiteren Schritte → Workflow abschliessen
            if not neue_tasks and not naechste_schritte.exists():
                offene_tasks = task.instance.tasks.filter(
                    status__in=["offen", "in_bearbeitung"]
                ).count()

                if offene_tasks == 0:
                    task.instance.status = "abgeschlossen"
                    task.instance.abgeschlossen_am = timezone.now()
                    task.instance.aktueller_schritt = None
                    task.instance.save()

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
