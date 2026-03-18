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
            name="Briefvorlage",
            fields=[
                ("id",           models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titel",        models.CharField(max_length=200)),
                ("beschreibung", models.TextField(blank=True)),
                ("inhalt",       models.BinaryField()),
                ("ist_aktiv",    models.BooleanField(default=True)),
                ("erstellt_am",  models.DateTimeField(auto_now_add=True)),
                ("erstellt_von", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="briefvorlagen",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name":        "Briefvorlage",
                "verbose_name_plural": "Briefvorlagen",
                "ordering":            ["titel"],
            },
        ),
        migrations.CreateModel(
            name="Briefvorgang",
            fields=[
                ("id",                  models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("absender_name",       models.CharField(max_length=200)),
                ("absender_strasse",    models.CharField(blank=True, max_length=200)),
                ("absender_ort",        models.CharField(blank=True, max_length=200)),
                ("absender_telefon",    models.CharField(blank=True, max_length=50)),
                ("absender_email",      models.CharField(blank=True, max_length=200)),
                ("empfaenger_name",     models.CharField(max_length=200)),
                ("empfaenger_zusatz",   models.CharField(blank=True, max_length=200)),
                ("empfaenger_strasse",  models.CharField(blank=True, max_length=200)),
                ("empfaenger_plz_ort",  models.CharField(blank=True, max_length=200)),
                ("empfaenger_land",     models.CharField(blank=True, max_length=200)),
                ("ort",                 models.CharField(max_length=100)),
                ("datum",               models.DateField()),
                ("betreff",             models.CharField(max_length=300)),
                ("anrede",              models.CharField(max_length=200)),
                ("brieftext",           models.TextField()),
                ("grussformel",         models.CharField(max_length=200, default="Mit freundlichen Gruessen")),
                ("unterschrift_name",   models.CharField(max_length=200)),
                ("unterschrift_titel",  models.CharField(blank=True, max_length=200)),
                ("inhalt",              models.BinaryField(blank=True, null=True)),
                ("version",             models.PositiveIntegerField(default=1)),
                ("status",              models.CharField(
                    choices=[("entwurf", "Entwurf"), ("fertig", "Fertig"), ("archiviert", "Archiviert")],
                    default="entwurf",
                    max_length=20,
                )),
                ("erstellt_am",         models.DateTimeField(auto_now_add=True)),
                ("geaendert_am",        models.DateTimeField(auto_now=True)),
                ("vorlage",             models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="vorgaenge",
                    to="korrespondenz.briefvorlage",
                )),
                ("erstellt_von",        models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="briefe",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name":        "Briefvorgang",
                "verbose_name_plural": "Briefvorgaenge",
                "ordering":            ["-erstellt_am"],
            },
        ),
    ]
