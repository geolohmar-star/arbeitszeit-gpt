import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sicherheit", "0003_branderkundertoken_notiz"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="brandalarm",
            name="nachbewertung",
            field=models.CharField(
                blank=True,
                choices=[
                    ("positiv", "Positiv – alles lief korrekt"),
                    ("verbesserungsbedarf", "Verbesserungsbedarf"),
                    ("kritisch", "Kritisch – Massnahmen erforderlich"),
                ],
                max_length=30,
                verbose_name="Nachbewertung",
            ),
        ),
        migrations.AddField(
            model_name="brandalarm",
            name="nachbewertung_erstellt_am",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="brandalarm",
            name="nachbewertung_erstellt_von",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bewertete_brandalarme",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Nachbewertung erstellt von",
            ),
        ),
        migrations.AddField(
            model_name="brandalarm",
            name="nachbewertung_text",
            field=models.TextField(blank=True, verbose_name="Nachbewertungstext"),
        ),
    ]
