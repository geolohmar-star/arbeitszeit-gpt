"""Workflow-Engine: Zentrale Logik fuer Workflow-Verwaltung

Phase 1 (MVP):
- start_workflow(): Workflow aus Template starten
- resolve_rolle(): Zustaendigkeiten aufloesen
- create_tasks(): Tasks erstellen
- complete_task(): Naechsten Schritt aktivieren
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from .models import WorkflowInstance, WorkflowStep, WorkflowTask

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

    def complete_task(self, task, entscheidung, kommentar, user):
        """Erledigt einen Task und aktiviert naechste Schritte.

        Args:
            task: WorkflowTask Instanz
            entscheidung: "genehmigt", "abgelehnt", etc.
            kommentar: Kommentar-Text
            user: User der die Entscheidung trifft

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

            # Workflow-Logik basierend auf Entscheidung
            if entscheidung == "abgelehnt":
                # Bei Ablehnung: Workflow abbrechen
                task.instance.status = "abgebrochen"
                task.instance.abgeschlossen_am = timezone.now()
                task.instance.save()
                return []

            # Naechsten Schritt(e) finden
            aktuelle_reihenfolge = task.step.reihenfolge
            naechste_reihenfolge = aktuelle_reihenfolge + 1

            naechste_schritte = task.instance.template.schritte.filter(
                reihenfolge=naechste_reihenfolge
            )

            if naechste_schritte.exists():
                # Naechste Schritte erstellen
                for schritt in naechste_schritte:
                    neue_tasks.extend(
                        self.create_tasks_for_step(
                            task.instance, schritt, task.instance.content_object
                        )
                    )

                # Aktuellen Schritt aktualisieren
                task.instance.aktueller_schritt = naechste_schritte.first()
                task.instance.save()
            else:
                # Keine weiteren Schritte → Workflow abschliessen
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
