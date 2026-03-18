from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dms", "0010_dokument_loeschkennzeichen"),
    ]

    operations = [
        migrations.AddField(
            model_name="dokument",
            name="ist_persoenlich",
            field=models.BooleanField(
                default=False,
                verbose_name="Persoenliche Ablage",
                help_text="True = Dokument gehoert zur persoenlichen Ablage des Erstellers.",
            ),
        ),
    ]
