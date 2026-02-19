"""Migration: OrgEinheit + Stelle + HRMitarbeiter.stelle

Schema-Migration erstellt die neuen Modelle OrgEinheit und Stelle
sowie das neue OneToOneField stelle am HRMitarbeiter.

Data-Migration legt die 9 reservierten Organisationseinheiten an.
"""

import django.db.models.deletion
from django.db import migrations, models


def erstelle_reservierte_org_einheiten(apps, schema_editor):
    """Legt die 9 reservierten Organisationseinheiten an."""
    OrgEinheit = apps.get_model("hr", "OrgEinheit")
    reservierte = [
        ("GF", "Geschaeftsfuehrung"),
        ("BV", "Betrieb und Verwaltung"),
        ("HR", "Human Resources"),
        ("IT", "Informationstechnik"),
        ("FM", "Facility Management"),
        ("VW", "Verwaltung"),
        ("PF", "Pflege"),
        ("KU", "Kueche"),
        ("TL", "Technik und Logistik"),
    ]
    for kuerzel, bezeichnung in reservierte:
        OrgEinheit.objects.get_or_create(
            kuerzel=kuerzel,
            defaults={"bezeichnung": bezeichnung, "ist_reserviert": True},
        )


def loesche_reservierte_org_einheiten(apps, schema_editor):
    """Macht die Data-Migration rueckgaengig (nur reservierte loeschen)."""
    OrgEinheit = apps.get_model("hr", "OrgEinheit")
    OrgEinheit.objects.filter(ist_reserviert=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hr", "0001_init"),
    ]

    operations = [
        # OrgEinheit erstellen
        migrations.CreateModel(
            name="OrgEinheit",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("bezeichnung", models.CharField(max_length=100)),
                ("ist_reserviert", models.BooleanField(default=False)),
                ("kuerzel", models.CharField(max_length=10, unique=True)),
                (
                    "uebergeordnet",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="untereinheiten",
                        to="hr.orgeinheit",
                        verbose_name="Uebergeordnete Einheit",
                    ),
                ),
            ],
            options={
                "verbose_name": "Organisationseinheit",
                "verbose_name_plural": "Organisationseinheiten",
                "ordering": ["kuerzel"],
            },
        ),
        # Stelle erstellen
        migrations.CreateModel(
            name="Stelle",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("bezeichnung", models.CharField(max_length=200)),
                (
                    "eskalation_nach_tagen",
                    models.PositiveIntegerField(
                        default=3, verbose_name="Eskalation nach (Tagen)"
                    ),
                ),
                ("kuerzel", models.CharField(max_length=20, unique=True)),
                (
                    "max_urlaubstage_genehmigung",
                    models.PositiveIntegerField(
                        default=0, verbose_name="Max. Urlaubstage Genehmigung"
                    ),
                ),
                ("vertretung_bis", models.DateField(blank=True, null=True)),
                ("vertretung_von", models.DateField(blank=True, null=True)),
                (
                    "delegiert_an",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="erhaelt_delegation",
                        to="hr.stelle",
                        verbose_name="Delegiert an",
                    ),
                ),
                (
                    "org_einheit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stellen",
                        to="hr.orgeinheit",
                        verbose_name="Organisationseinheit",
                    ),
                ),
                (
                    "uebergeordnete_stelle",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="untergeordnete_stellen",
                        to="hr.stelle",
                        verbose_name="Uebergeordnete Stelle",
                    ),
                ),
                (
                    "vertreten_durch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="vertritt_stellen",
                        to="hr.stelle",
                        verbose_name="Vertreten durch",
                    ),
                ),
            ],
            options={
                "verbose_name": "Stelle",
                "verbose_name_plural": "Stellen",
                "ordering": ["kuerzel"],
            },
        ),
        # stelle-FK zu HRMitarbeiter hinzufuegen
        migrations.AddField(
            model_name="hrmitarbeiter",
            name="stelle",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="hrmitarbeiter",
                to="hr.stelle",
                verbose_name="Stelle",
            ),
        ),
        # Data-Migration: reservierte OrgEinheiten anlegen
        migrations.RunPython(
            erstelle_reservierte_org_einheiten,
            reverse_code=loesche_reservierte_org_einheiten,
        ),
    ]
