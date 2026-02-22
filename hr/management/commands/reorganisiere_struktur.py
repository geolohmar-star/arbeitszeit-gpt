"""
Management Command: Reorganisiert die Unternehmensstruktur.

Zielstruktur:
- Geschaeftsfuehrung (GF)
  - gf1 (Geschaeftsfuehrer)
    - Verwaltung (VW)
      - BL Finanzen & Controlling
        - Buchhaltung, Controlling, Lohn & Gehalt
      - BL Personal
        - HR, PE, PG, PV
      - BL IT & Digitalisierung
        - IT, DA, II
      - BL Administration
        - FM, EL, ZA
    - Produktion & Technik (PT)
      - BL Produktion & Technik
        - TE, PR, QS, SE
    - Vertrieb & Marketing (VM)
      - BL Vertrieb & Marketing
        - MK, AD, ID
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from hr.models import OrgEinheit, Stelle


class Command(BaseCommand):
    help = "Reorganisiert die Unternehmensstruktur in eine sinnvolle Hierarchie"

    def add_arguments(self, parser):
        parser.add_argument(
            '--execute',
            action='store_true',
            help='Fuehrt die Reorganisation durch (ohne dieses Flag nur Vorschau)',
        )

    def handle(self, *args, **options):
        execute = options['execute']

        if not execute:
            self.stdout.write(self.style.WARNING('=== VORSCHAU-MODUS ==='))
            self.stdout.write('Fuehre mit --execute aus um Aenderungen zu speichern\n')

        self.stdout.write(self.style.SUCCESS('Starte Reorganisation...'))

        with transaction.atomic():
            # 1. Hole/Erstelle GF
            gf, _ = OrgEinheit.objects.get_or_create(
                kuerzel='GF',
                defaults={'bezeichnung': 'Geschaeftsfuehrung', 'ist_reserviert': True}
            )
            gf.uebergeordnet = None
            gf.leitende_stelle = None
            if execute:
                gf.save()
            self.stdout.write(f'[OK] GF: {gf.bezeichnung}')

            # 2. GF-Stelle erstellen/holen
            gf1, created = Stelle.objects.get_or_create(
                kuerzel='gf1',
                defaults={
                    'bezeichnung': 'Geschaeftsfuehrer/in',
                    'kategorie': Stelle.KATEGORIE_LEITUNG,
                    'org_einheit': gf
                }
            )
            if created:
                self.stdout.write(f'  + Erstellt: {gf1.kuerzel} - {gf1.bezeichnung}')
            else:
                gf1.kategorie = Stelle.KATEGORIE_LEITUNG
                gf1.org_einheit = gf
                if execute:
                    gf1.save()
                self.stdout.write(f'  + Aktualisiert: {gf1.kuerzel}')

            # 3. Verwaltung (VW) erstellen
            vw, _ = OrgEinheit.objects.get_or_create(
                kuerzel='VW',
                defaults={'bezeichnung': 'Verwaltung'}
            )
            vw.uebergeordnet = gf
            vw.leitende_stelle = None
            if execute:
                vw.save()
            self.stdout.write(f'\n[OK] VW: {vw.bezeichnung}')

            # 4. Bereichsleiter Verwaltung
            bereichsleiter_vw = [
                {
                    'kuerzel': 'bl_finanzen',
                    'bezeichnung': 'Bereichsleiter/in Finanzen & Controlling',
                    'abteilungen': ['BH', 'CO', 'LG']
                },
                {
                    'kuerzel': 'bl_personal',
                    'bezeichnung': 'Bereichsleiter/in Personal',
                    'abteilungen': ['HR', 'PE', 'PG', 'PV']
                },
                {
                    'kuerzel': 'bl_it_digital',
                    'bezeichnung': 'Bereichsleiter/in IT & Digitalisierung',
                    'abteilungen': ['IT', 'DA', 'II']
                },
                {
                    'kuerzel': 'bl_admin',
                    'bezeichnung': 'Bereichsleiter/in Administration',
                    'abteilungen': ['FM', 'EL', 'ZA']
                }
            ]

            for bl_data in bereichsleiter_vw:
                bl, created = Stelle.objects.get_or_create(
                    kuerzel=bl_data['kuerzel'],
                    defaults={
                        'bezeichnung': bl_data['bezeichnung'],
                        'kategorie': Stelle.KATEGORIE_LEITUNG,
                        'org_einheit': vw,
                        'uebergeordnete_stelle': None
                    }
                )
                if not created:
                    bl.kategorie = Stelle.KATEGORIE_LEITUNG
                    bl.org_einheit = vw
                    bl.uebergeordnete_stelle = None
                    if execute:
                        bl.save()

                self.stdout.write(f'  + {bl.kuerzel}: {bl.bezeichnung}')

                # Abteilungen zuordnen
                for abt_kuerzel in bl_data['abteilungen']:
                    try:
                        abt = OrgEinheit.objects.get(kuerzel=abt_kuerzel)
                        abt.uebergeordnet = vw
                        abt.leitende_stelle = bl
                        if execute:
                            abt.save()
                        self.stdout.write(f'    - {abt.kuerzel}: {abt.bezeichnung}')
                    except OrgEinheit.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f'    ! {abt_kuerzel} nicht gefunden')
                        )

            # 5. Produktion & Technik (PT)
            pt, _ = OrgEinheit.objects.get_or_create(
                kuerzel='PT',
                defaults={'bezeichnung': 'Produktion & Technik'}
            )
            pt.uebergeordnet = gf
            pt.leitende_stelle = None
            if execute:
                pt.save()
            self.stdout.write(f'\n[OK] PT: {pt.bezeichnung}')

            bl_prod, created = Stelle.objects.get_or_create(
                kuerzel='bl_produktion',
                defaults={
                    'bezeichnung': 'Bereichsleiter/in Produktion & Technik',
                    'kategorie': Stelle.KATEGORIE_LEITUNG,
                    'org_einheit': pt,
                    'uebergeordnete_stelle': None
                }
            )
            if not created:
                bl_prod.kategorie = Stelle.KATEGORIE_LEITUNG
                bl_prod.org_einheit = pt
                bl_prod.uebergeordnete_stelle = None
                if execute:
                    bl_prod.save()

            self.stdout.write(f'  + {bl_prod.kuerzel}: {bl_prod.bezeichnung}')

            for abt_kuerzel in ['TE', 'PR', 'QS', 'SE']:
                try:
                    abt = OrgEinheit.objects.get(kuerzel=abt_kuerzel)
                    abt.uebergeordnet = pt
                    abt.leitende_stelle = bl_prod
                    if execute:
                        abt.save()
                    self.stdout.write(f'    - {abt.kuerzel}: {abt.bezeichnung}')
                except OrgEinheit.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f'    ! {abt_kuerzel} nicht gefunden')
                    )

            # 6. Vertrieb & Marketing (VM) bleibt direkt unter GF
            try:
                vm = OrgEinheit.objects.get(kuerzel='VM')
                vm.uebergeordnet = gf
                if execute:
                    vm.save()
                self.stdout.write(f'\n[OK] VM: {vm.bezeichnung}')

                bl_vm, created = Stelle.objects.get_or_create(
                    kuerzel='bl_vertrieb',
                    defaults={
                        'bezeichnung': 'Bereichsleiter/in Vertrieb & Marketing',
                        'kategorie': Stelle.KATEGORIE_LEITUNG,
                        'org_einheit': vm,
                        'uebergeordnete_stelle': None
                    }
                )
                if not created:
                    bl_vm.kategorie = Stelle.KATEGORIE_LEITUNG
                    bl_vm.org_einheit = vm
                    bl_vm.uebergeordnete_stelle = None
                    if execute:
                        bl_vm.save()

                self.stdout.write(f'  + {bl_vm.kuerzel}: {bl_vm.bezeichnung}')

                vm.leitende_stelle = bl_vm
                if execute:
                    vm.save()

                # VM Unterabteilungen
                for abt_kuerzel in ['MK', 'AD', 'ID']:
                    try:
                        abt = OrgEinheit.objects.get(kuerzel=abt_kuerzel)
                        abt.uebergeordnet = vm
                        if execute:
                            abt.save()
                        self.stdout.write(f'    - {abt.kuerzel}: {abt.bezeichnung}')
                    except OrgEinheit.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f'    ! {abt_kuerzel} nicht gefunden')
                        )
            except OrgEinheit.DoesNotExist:
                self.stdout.write(self.style.WARNING('  ! VM nicht gefunden'))

            # 7. Alte BV-Struktur aufloesen
            try:
                bv = OrgEinheit.objects.get(kuerzel='BV')
                # Alle Stellen die noch zu BV gehoeren zu GF verschieben
                Stelle.objects.filter(org_einheit=bv).update(org_einheit=gf)
                if execute:
                    bv.delete()
                self.stdout.write(f'\n[OK] BV geloescht (Stellen zu GF verschoben)')
            except OrgEinheit.DoesNotExist:
                pass

            if not execute:
                self.stdout.write(
                    self.style.WARNING(
                        '\n=== VORSCHAU BEENDET ===\nKeine Aenderungen gespeichert!'
                    )
                )
                raise transaction.TransactionManagementError('Rollback (Vorschau)')
            else:
                self.stdout.write(self.style.SUCCESS('\n=== REORGANISATION ABGESCHLOSSEN ==='))
