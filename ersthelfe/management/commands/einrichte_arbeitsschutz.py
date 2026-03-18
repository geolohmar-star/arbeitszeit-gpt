"""
Management-Command: Abteilung Arbeitsschutz anlegen

Struktur:
  VW – Verwaltung
  └── AS – Arbeitsschutz
        ├── al_as  Abteilungsleiter/in Arbeitsschutz   (Leitung, Kategorie: leitung)
        └── ba_as  Betriebsarzt/Betriebsaerztin         (Stab,    Kategorie: stab)

Beide Stellen sind gleichrangig (keine ist der anderen uebergeordnet).
Die Stelle ba_as wird aus der bisherigen OrgEinheit in AS verschoben.

Ausfuehren:
    python manage.py einrichte_arbeitsschutz
    python manage.py einrichte_arbeitsschutz --ueberschreiben
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Legt OrgEinheit Arbeitsschutz an und integriert Betriebsarzt"

    def add_arguments(self, parser):
        parser.add_argument("--ueberschreiben", action="store_true",
                            help="Vorhandene Eintraege aktualisieren")

    def handle(self, *args, **options):
        ue = options["ueberschreiben"]
        self._org_einheit_anlegen(ue)
        self._al_as_anlegen(ue)
        self._betriebsarzt_eingliedern(ue)
        self._ergebnis_zeigen()

    # -----------------------------------------------------------------------

    def _org_einheit_anlegen(self, ueberschreiben):
        from hr.models import OrgEinheit

        self.stdout.write("\n--- OrgEinheit Arbeitsschutz ---")

        try:
            vw = OrgEinheit.objects.get(kuerzel="VW")
        except OrgEinheit.DoesNotExist:
            # Fallback: direkt unter GF
            try:
                vw = OrgEinheit.objects.get(kuerzel="GF")
            except OrgEinheit.DoesNotExist:
                vw = None

        oe, neu = OrgEinheit.objects.get_or_create(
            kuerzel="AS",
            defaults={
                "bezeichnung": "Arbeitsschutz",
                "uebergeordnet": vw,
            },
        )
        if not neu and ueberschreiben:
            oe.bezeichnung = "Arbeitsschutz"
            oe.uebergeordnet = vw
            oe.save()

        status = "angelegt" if neu else ("aktualisiert" if ueberschreiben else "bereits vorhanden")
        self.stdout.write(self.style.SUCCESS(
            f"  OrgEinheit 'AS – Arbeitsschutz' {status}"
            + (f" (unter: {vw.kuerzel})" if vw else "")
        ))

    def _al_as_anlegen(self, ueberschreiben):
        from hr.models import HRMitarbeiter, OrgEinheit, Stelle

        self.stdout.write("\n--- Stelle al_as (Abteilungsleiter/in Arbeitsschutz) ---")

        as_oe = OrgEinheit.objects.get(kuerzel="AS")

        stelle, neu = Stelle.objects.get_or_create(
            kuerzel="al_as",
            defaults={
                "bezeichnung": "Abteilungsleiter/in Arbeitsschutz",
                "org_einheit": as_oe,
                "kategorie": "leitung",
            },
        )
        if not neu and ueberschreiben:
            stelle.bezeichnung = "Abteilungsleiter/in Arbeitsschutz"
            stelle.org_einheit = as_oe
            stelle.kategorie = "leitung"
            stelle.save()

        status = "angelegt" if neu else ("aktualisiert" if ueberschreiben else "bereits vorhanden")
        self.stdout.write(self.style.SUCCESS(f"  Stelle 'al_as' {status}."))

        # Besetzen falls noch frei
        if stelle.ist_besetzt:
            self.stdout.write(f"  Inhaber: {stelle.hrmitarbeiter.vollname} – unveraendert.")
            return

        kandidat = (
            HRMitarbeiter.objects.filter(stelle__isnull=True, user__isnull=False)
            .order_by("nachname")
            .first()
        )
        if not kandidat:
            self.stdout.write(self.style.WARNING(
                "  Kein freier Mitarbeiter verfuegbar – Stelle bleibt unbesetzt."
            ))
            return

        kandidat.stelle = stelle
        kandidat.save(update_fields=["stelle"])
        self.stdout.write(self.style.SUCCESS(
            f"  {kandidat.vollname} ({kandidat.personalnummer}) als AL Arbeitsschutz eingestellt."
        ))

    def _betriebsarzt_eingliedern(self, ueberschreiben):
        from hr.models import OrgEinheit, Stelle

        self.stdout.write("\n--- Betriebsarzt in Arbeitsschutz eingliedern ---")

        try:
            ba_as = Stelle.objects.get(kuerzel="ba_as")
        except Stelle.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                "  Stelle 'ba_as' nicht gefunden – zuerst 'ersthelfe_einrichten' ausfuehren."
            ))
            return

        as_oe = OrgEinheit.objects.get(kuerzel="AS")

        if ba_as.org_einheit == as_oe and not ueberschreiben:
            self.stdout.write(f"  ba_as bereits in OE 'AS' – unveraendert.")
            return

        alte_oe = ba_as.org_einheit.kuerzel if ba_as.org_einheit else "(keine)"
        ba_as.org_einheit = as_oe
        ba_as.kategorie = "stab"
        # Kein uebergeordnete_stelle setzen – gleiche Ebene wie al_as
        ba_as.uebergeordnete_stelle = None
        ba_as.save(update_fields=["org_einheit", "kategorie", "uebergeordnete_stelle"])

        inhaber = getattr(ba_as, "hrmitarbeiter", None)
        self.stdout.write(self.style.SUCCESS(
            f"  ba_as von OE '{alte_oe}' nach 'AS' verschoben"
            + (f" (Inhaber: {inhaber.vollname})" if inhaber else "")
            + "."
        ))

        # al_as ebenfalls kein uebergeordnete_stelle – beide gleichrangig
        try:
            al_as = Stelle.objects.get(kuerzel="al_as")
            if al_as.uebergeordnete_stelle is not None:
                al_as.uebergeordnete_stelle = None
                al_as.save(update_fields=["uebergeordnete_stelle"])
        except Stelle.DoesNotExist:
            pass

        self.stdout.write("  Beide Stellen (al_as, ba_as) sind gleichrangig – keine ist der anderen vorgeordnet.")

    def _ergebnis_zeigen(self):
        from hr.models import OrgEinheit, Stelle

        self.stdout.write("\n=== Ergebnis: OrgEinheit AS – Arbeitsschutz ===")
        try:
            as_oe = OrgEinheit.objects.get(kuerzel="AS")
            ue = as_oe.uebergeordnet
            self.stdout.write(f"  Uebergeordnet: {ue.kuerzel + ' – ' + ue.bezeichnung if ue else '(Wurzel)'}")
        except OrgEinheit.DoesNotExist:
            return

        for stelle in Stelle.objects.filter(org_einheit=as_oe).select_related("org_einheit"):
            inhaber = getattr(stelle, "hrmitarbeiter", None)
            rang = "Leitung" if stelle.kategorie == "leitung" else "Stab"
            self.stdout.write(
                f"  [{rang:7}]  {stelle.kuerzel:8}  {stelle.bezeichnung:35}"
                f"  Inhaber: {inhaber.vollname if inhaber else '(unbesetzt)'}"
            )
