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
            name="SicherheitsAlarm",
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
                ("erstellt_am", models.DateTimeField(auto_now_add=True)),
                ("geschlossen_am", models.DateTimeField(blank=True, null=True)),
                ("notiz", models.TextField(blank=True)),
                ("ort", models.CharField(blank=True, max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("aktiv", "Aktiv"),
                            ("geschlossen", "Geschlossen"),
                        ],
                        default="aktiv",
                        max_length=20,
                    ),
                ),
                (
                    "typ",
                    models.CharField(
                        choices=[
                            ("amok", "AMOK-Alarm"),
                            ("still", "Stiller Alarm"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "ausgeloest_von",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ausgeloeste_alarme",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "geschlossen_von",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="geschlossene_alarme",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Sicherheitsalarm",
                "verbose_name_plural": "Sicherheitsalarme",
                "ordering": ["-erstellt_am"],
            },
        ),
    ]
