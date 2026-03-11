# -*- coding: utf-8 -*-
"""Data-Migration: Abteilung DMS/Archiv mit Stellen, Personen, Team und DMS-Admin-Gruppe."""

from django.db import migrations


def erstelle_dms_archiv(apps, schema_editor):
    # Modelle ueber den historischen Registry holen
    Bereich = apps.get_model("hr", "Bereich")
    Abteilung = apps.get_model("hr", "Abteilung")
    OrgEinheit = apps.get_model("hr", "OrgEinheit")
    Stelle = apps.get_model("hr", "Stelle")
    HRMitarbeiter = apps.get_model("hr", "HRMitarbeiter")
    Team = apps.get_model("hr", "Team")
    User = apps.get_model("auth", "User")
    Group = apps.get_model("auth", "Group")
    TeamQueue = apps.get_model("formulare", "TeamQueue")

    # --- Bereich (BV – Betrieb & Verwaltung) ---
    bv = Bereich.objects.get(kuerzel="BV")

    # --- Abteilung ---
    abteilung, _ = Abteilung.objects.get_or_create(
        kuerzel="DMS",
        bereich=bv,
        defaults={"name": "DMS & Archiv"},
    )

    # --- OrgEinheit ---
    org, _ = OrgEinheit.objects.get_or_create(
        kuerzel="ARC",
        defaults={"bezeichnung": "DMS & Archiv", "ist_reserviert": True},
    )

    # --- Stellen anlegen ---
    # AL
    al_stelle, _ = Stelle.objects.get_or_create(
        kuerzel="al_arc",
        defaults={
            "bezeichnung": "Leiter/in DMS & Archiv",
            "kategorie": "leitung",
            "org_einheit": org,
            "eskalation_nach_tagen": 2,
        },
    )
    # SV
    sv_stelle, _ = Stelle.objects.get_or_create(
        kuerzel="sv_arc",
        defaults={
            "bezeichnung": "Sachbearbeiter/in DMS & Archiv",
            "kategorie": "stab",
            "org_einheit": org,
            "uebergeordnete_stelle": al_stelle,
            "eskalation_nach_tagen": 3,
        },
    )
    # MA 1-5
    ma_stellen = []
    for i in range(1, 6):
        ma, _ = Stelle.objects.get_or_create(
            kuerzel=f"ma_arc{i}",
            defaults={
                "bezeichnung": f"Archivmitarbeiter/in {i}",
                "kategorie": "fachkraft",
                "org_einheit": org,
                "uebergeordnete_stelle": sv_stelle,
                "eskalation_nach_tagen": 3,
            },
        )
        ma_stellen.append(ma)

    # OrgEinheit-Leitung setzen
    org.leitende_stelle = al_stelle
    org.save()

    # --- Personen erstellen ---
    # Hilfsfunktion: naechste Personalnummer
    import random
    def naechste_pnr():
        vorhandene = set(
            HRMitarbeiter.objects.filter(
                personalnummer__regex=r"^\d{5}$"
            ).values_list("personalnummer", flat=True)
        )
        n = max((int(p) for p in vorhandene), default=10000) + 1
        while str(n) in vorhandene:
            n += 1
        return str(n)

    personen = [
        # (vorname, nachname, rolle, stelle, is_staff)
        ("Klaus",    "Hartmann", "abteilungsleiter", al_stelle, True),
        ("Petra",    "Schneider", "assistent",       sv_stelle, False),
        ("Thomas",   "Bauer",     "mitarbeiter",     ma_stellen[0], False),
        ("Sabine",   "Koch",      "mitarbeiter",     ma_stellen[1], False),
        ("Michael",  "Wagner",    "mitarbeiter",     ma_stellen[2], False),
        ("Andrea",   "Fischer",   "mitarbeiter",     ma_stellen[3], False),
        ("Stefan",   "Mueller",   "mitarbeiter",     ma_stellen[4], False),
    ]

    erstellte_user = []
    for vorname, nachname, rolle, stelle, is_staff in personen:
        pnr = naechste_pnr()
        username = f"{vorname.lower()}.{nachname.lower()}.AP-{pnr}"
        if User.objects.filter(username=username).exists():
            user = User.objects.get(username=username)
        else:
            user = User.objects.create_user(
                username=username,
                first_name=vorname,
                last_name=nachname,
                email=f"{stelle.kuerzel}@firma.de",
                password="Prima2026!",
                is_staff=is_staff,
            )
        if not HRMitarbeiter.objects.filter(stelle=stelle).exists():
            ma = HRMitarbeiter.objects.create(
                user=user,
                vorname=vorname,
                nachname=nachname,
                personalnummer=pnr,
                rolle=rolle,
                bereich=bv,
                abteilung=abteilung,
                stelle=stelle,
                eintrittsdatum="2026-03-10",
            )
        erstellte_user.append(user)

    # --- Team (hr.Team) ---
    team, _ = Team.objects.get_or_create(
        name="DMS & Archiv",
        abteilung=abteilung,
    )
    # Alle MA dem Team zuweisen
    HRMitarbeiter.objects.filter(abteilung=abteilung).update(team=team)

    # --- TeamQueue ---
    tq, _ = TeamQueue.objects.get_or_create(
        kuerzel="dms",
        defaults={"name": "DMS & Archiv"},
    )
    for user in erstellte_user:
        tq.mitglieder.add(user)

    # --- Django-Gruppe DMS-Admin ---
    gruppe, _ = Group.objects.get_or_create(name="DMS-Admin")
    # AL-User zur Gruppe hinzufuegen
    al_user = erstellte_user[0]
    al_user.groups.add(gruppe)


def entferne_dms_archiv(apps, schema_editor):
    # Rollback: Personen und Stellen entfernen
    User = apps.get_model("auth", "User")
    Group = apps.get_model("auth", "Group")
    HRMitarbeiter = apps.get_model("hr", "HRMitarbeiter")
    Stelle = apps.get_model("hr", "Stelle")
    OrgEinheit = apps.get_model("hr", "OrgEinheit")
    Abteilung = apps.get_model("hr", "Abteilung")
    Team = apps.get_model("hr", "Team")
    TeamQueue = apps.get_model("formulare", "TeamQueue")
    Bereich = apps.get_model("hr", "Bereich")

    stellen_kuerzel = ["al_arc", "sv_arc", "ma_arc1", "ma_arc2", "ma_arc3", "ma_arc4", "ma_arc5"]
    for ma in HRMitarbeiter.objects.filter(stelle__kuerzel__in=stellen_kuerzel):
        if ma.user:
            ma.user.delete()
    Stelle.objects.filter(kuerzel__in=stellen_kuerzel).delete()
    try:
        bv = Bereich.objects.get(kuerzel="BV")
        Team.objects.filter(name="DMS & Archiv", abteilung__bereich=bv).delete()
        Abteilung.objects.filter(kuerzel="DMS", bereich=bv).delete()
    except Exception:
        pass
    OrgEinheit.objects.filter(kuerzel="ARC").delete()
    TeamQueue.objects.filter(kuerzel="dms").delete()
    Group.objects.filter(name="DMS-Admin").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hr", "0009_personalstammdaten"),
        ("formulare", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(erstelle_dms_archiv, entferne_dms_archiv),
    ]
