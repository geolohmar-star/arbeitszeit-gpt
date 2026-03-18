from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("hr", "0012_brandschutz_felder"),
        ("sicherheit", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Brandalarm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("erstellt_am", models.DateTimeField(auto_now_add=True)),
                ("melder_anzahl", models.PositiveSmallIntegerField(default=1, help_text="Erhoeht sich wenn ein zweiter Nutzer meldet", verbose_name="Anzahl Meldungen")),
                ("notiz", models.TextField(blank=True, verbose_name="Notiz")),
                ("ort", models.CharField(help_text="Vom Melder angegebener oder aus Buero ermittelter Ort", max_length=200, verbose_name="Gemeldeter Ort")),
                ("ort_praezise", models.CharField(blank=True, help_text="Vom Branderkunder praezisierter Brandort", max_length=200, verbose_name="Praeziser Ort")),
                ("security_bestaetigt_am", models.DateTimeField(blank=True, null=True)),
                ("geschlossen_am", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(
                    choices=[
                        ("gemeldet", "Gemeldet – Branderkunder unterwegs"),
                        ("bestaetigung", "Bestaetigung ausstehend – Security-Review"),
                        ("evakuierung", "Evakuierung aktiv"),
                        ("geschlossen", "Geschlossen / Entwarnung"),
                    ],
                    default="gemeldet",
                    max_length=20,
                    verbose_name="Status",
                )),
                ("gemeldet_von", models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="gemeldete_brandalarme",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="Gemeldet von",
                )),
                ("geschlossen_von", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="geschlossene_brandalarme",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="Geschlossen von",
                )),
                ("security_bestaetigt_von", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="bestaetigte_brandalarme",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="Security-Bestaetigung von",
                )),
            ],
            options={"ordering": ["-erstellt_am"], "verbose_name": "Brandalarm", "verbose_name_plural": "Brandalarme"},
        ),
        migrations.CreateModel(
            name="BranderkunderToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("erstellt_am", models.DateTimeField(auto_now_add=True)),
                ("matrix_dm_room_id", models.CharField(blank=True, max_length=200)),
                ("ort_praezise", models.CharField(blank=True, help_text="Vom Branderkunder gemeldeter praeziser Brandort", max_length=200, verbose_name="Wo genau?")),
                ("status", models.CharField(
                    choices=[
                        ("ausstehend", "Ausstehend"),
                        ("unterwegs", "Bin auf dem Weg"),
                        ("bestaetigt", "Brand bestaetigt"),
                        ("fehlalarm", "Kein Brand / Fehlalarm"),
                    ],
                    default="ausstehend",
                    max_length=20,
                )),
                ("token", models.CharField(editable=False, max_length=64, unique=True)),
                ("brandalarm", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="erkunder_tokens",
                    to="sicherheit.brandalarm",
                    verbose_name="Brandalarm",
                )),
                ("erkunder", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="brand_tokens",
                    to="hr.hrmitarbeiter",
                    verbose_name="Branderkunder/in",
                )),
            ],
            options={"ordering": ["-erstellt_am"], "verbose_name": "Branderkunder-Token", "verbose_name_plural": "Branderkunder-Tokens"},
        ),
    ]
