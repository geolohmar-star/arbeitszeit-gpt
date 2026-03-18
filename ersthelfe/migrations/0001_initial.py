from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("hr", "0010_dms_archiv_abteilung"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ErsteHilfeVorfall",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("beschreibung", models.TextField(blank=True, verbose_name="Beschreibung", help_text="Optionale Beschreibung der Situation")),
                ("erstellt_am", models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")),
                ("geschlossen_am", models.DateTimeField(blank=True, null=True, verbose_name="Geschlossen am")),
                ("ort", models.CharField(max_length=200, verbose_name="Ort", help_text="Wo ist der Notfall?")),
                ("status", models.CharField(
                    choices=[("offen", "Offen"), ("abgeschlossen", "Abgeschlossen")],
                    default="offen",
                    max_length=20,
                    verbose_name="Status",
                )),
                ("gemeldet_von", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="eh_vorfaelle",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="Gemeldet von",
                )),
            ],
            options={
                "verbose_name": "Erste-Hilfe-Vorfall",
                "verbose_name_plural": "Erste-Hilfe-Vorfaelle",
                "ordering": ["-erstellt_am"],
                "permissions": [
                    ("view_alle_vorfaelle", "Kann alle Erste-Hilfe-Vorfaelle einsehen"),
                    ("schliessen_vorfall", "Kann Erste-Hilfe-Vorfall abschliessen"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ErsteHilfeErsthelferToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("erstellt_am", models.DateTimeField(auto_now_add=True)),
                ("token", models.CharField(max_length=64, unique=True, verbose_name="Token")),
                ("ersthelfer", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="eh_tokens",
                    to="hr.hrmitarbeiter",
                    verbose_name="Ersthelfer/in",
                )),
                ("vorfall", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="ersthelfer_tokens",
                    to="ersthelfe.erstehilfevorfall",
                    verbose_name="Vorfall",
                )),
            ],
            options={
                "verbose_name": "Ersthelfer-Token",
                "verbose_name_plural": "Ersthelfer-Tokens",
                "ordering": ["-erstellt_am"],
                "unique_together": {("vorfall", "ersthelfer")},
            },
        ),
        migrations.CreateModel(
            name="ErsteHilfeRueckmeldung",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("gemeldet_am", models.DateTimeField(auto_now_add=True)),
                ("notiz", models.CharField(blank=True, max_length=200, verbose_name="Notiz", help_text="Optionaler Freitext")),
                ("status", models.CharField(
                    choices=[
                        ("unterwegs", "Bin unterwegs"),
                        ("am_ort", "Bin vor Ort"),
                        ("brauche_unterstuetzung", "Brauche Unterstuetzung"),
                        ("nicht_verfuegbar", "Kann nicht kommen"),
                    ],
                    max_length=30,
                    verbose_name="Status",
                )),
                ("ersthelfer", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="eh_rueckmeldungen",
                    to="hr.hrmitarbeiter",
                    verbose_name="Ersthelfer/in",
                )),
                ("vorfall", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="rueckmeldungen",
                    to="ersthelfe.erstehilfevorfall",
                    verbose_name="Vorfall",
                )),
            ],
            options={
                "verbose_name": "EH-Rueckmeldung",
                "verbose_name_plural": "EH-Rueckmeldungen",
                "ordering": ["-gemeldet_am"],
            },
        ),
    ]
