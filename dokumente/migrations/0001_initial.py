import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SensiblesDokument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kategorie", models.CharField(
                    choices=[
                        ("zeugnis", "Zeugnis"),
                        ("abschluss", "Abschluss / Qualifikation"),
                        ("reise", "Reiseunterlage"),
                        ("ausweis", "Ausweis / Identitaetsnachweis"),
                        ("sonstige", "Sonstiges"),
                    ],
                    max_length=20,
                    verbose_name="Kategorie",
                )),
                ("dateiname", models.CharField(max_length=255, verbose_name="Originaldateiname")),
                ("dateityp", models.CharField(max_length=100, verbose_name="MIME-Typ")),
                ("inhalt_verschluesselt", models.BinaryField(verbose_name="Inhalt (AES-verschluesselt)")),
                ("groesse_bytes", models.IntegerField(verbose_name="Dateigroesse (Bytes)")),
                ("beschreibung", models.CharField(blank=True, max_length=500, verbose_name="Beschreibung")),
                ("gueltig_bis", models.DateField(blank=True, null=True, verbose_name="Gueltig bis")),
                ("hochgeladen_am", models.DateTimeField(auto_now_add=True, verbose_name="Hochgeladen am")),
                ("hochgeladen_von", models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="hochgeladene_dokumente",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="Hochgeladen von",
                )),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="sensible_dokumente",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="Gehoert zu Mitarbeiter",
                )),
            ],
            options={
                "verbose_name": "Sensibles Dokument",
                "verbose_name_plural": "Sensible Dokumente",
                "ordering": ["-hochgeladen_am"],
            },
        ),
    ]
