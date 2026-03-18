from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sicherheit", "0002_brandalarm"),
    ]

    operations = [
        migrations.AddField(
            model_name="branderkundertoken",
            name="notiz",
            field=models.TextField(
                blank=True,
                verbose_name="Freitext-Meldung",
                help_text="Lagemeldung oder freie Nachricht des Branderkunder",
            ),
        ),
    ]
