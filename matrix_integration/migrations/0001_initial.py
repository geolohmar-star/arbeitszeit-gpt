import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("hr", "__first__"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TeilnehmerTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("typ", models.CharField(choices=[("org_einheit", "Aus Org-Einheit (automatisch)"), ("manuell", "Manuell zusammengestellt")], default="manuell", max_length=20)),
                ("beschreibung", models.TextField(blank=True)),
                ("org_einheit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="matrix_templates", to="hr.orgeinheit", verbose_name="Org-Einheit")),
                ("mitglieder", models.ManyToManyField(blank=True, related_name="matrix_templates", to=settings.AUTH_USER_MODEL, verbose_name="Manuelle Mitglieder")),
            ],
            options={"verbose_name": "Teilnehmer-Template", "verbose_name_plural": "Teilnehmer-Templates", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="MatrixRaum",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("typ", models.CharField(choices=[("bereich", "Bereichs-Chat"), ("abteilung", "Abteilungs-Chat"), ("team", "Team-Chat"), ("manuell", "Manueller Chat"), ("ping", "Ping-Kanal (Benachrichtigungen)")], default="manuell", max_length=20)),
                ("room_id", models.CharField(blank=True, default="", help_text="z.B. !IsrMLfIlLxJXrAIUKr:georg-klein.com", max_length=200, verbose_name="Matrix Room-ID")),
                ("room_alias", models.CharField(blank=True, default="", help_text="z.B. #team-it:georg-klein.com", max_length=200, verbose_name="Room-Alias")),
                ("element_url", models.URLField(blank=True, default="", help_text="z.B. https://app.element.io/#/room/!ID:georg-klein.com", verbose_name="Element-URL")),
                ("ping_typ", models.CharField(blank=True, choices=[("allgemein", "Allgemein"), ("facility", "Facility / Stoermeldungen"), ("hr", "HR / Personal"), ("it", "IT / Technik"), ("sicherheit", "Sicherheit")], default="", max_length=20, verbose_name="Ping-Kanal-Typ")),
                ("beschreibung", models.TextField(blank=True)),
                ("ist_aktiv", models.BooleanField(default=True)),
                ("org_einheit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="matrix_raeume", to="hr.orgeinheit", verbose_name="Org-Einheit")),
                ("teilnehmer_template", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="matrix_raeume", to="matrix_integration.teilnehmertemplate", verbose_name="Teilnehmer-Template")),
            ],
            options={"verbose_name": "Matrix-Raum", "verbose_name_plural": "Matrix-Raeume", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="SitzungsKalender",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("beschreibung", models.TextField(blank=True)),
                ("von", models.TimeField(verbose_name="Von")),
                ("bis", models.TimeField(verbose_name="Bis")),
                ("start_datum", models.DateField(verbose_name="Startdatum")),
                ("ende_datum", models.DateField(blank=True, null=True, verbose_name="Enddatum")),
                ("ist_wiederkehrend", models.BooleanField(default=False, verbose_name="Wiederkehrend")),
                ("wochentag", models.IntegerField(blank=True, choices=[(0, "Montag"), (1, "Dienstag"), (2, "Mittwoch"), (3, "Donnerstag"), (4, "Freitag"), (5, "Samstag"), (6, "Sonntag")], null=True, verbose_name="Wochentag")),
                ("erinnerung_minuten", models.IntegerField(default=15, verbose_name="Erinnerung (Minuten vorher)")),
                ("naechste_ausfuehrung", models.DateTimeField(blank=True, null=True, verbose_name="Naechste Ausfuehrung")),
                ("ist_aktiv", models.BooleanField(default=True)),
                ("matrix_raum", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sitzungen", to="matrix_integration.matrixraum", verbose_name="Matrix-Raum")),
                ("teilnehmer_template", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sitzungen", to="matrix_integration.teilnehmertemplate", verbose_name="Teilnehmer-Template")),
            ],
            options={"verbose_name": "Sitzungs-Kalender", "verbose_name_plural": "Sitzungs-Kalender", "ordering": ["naechste_ausfuehrung", "name"]},
        ),
    ]
