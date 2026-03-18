from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sicherheit", "0004_brandalarm_nachbewertung"),
    ]

    operations = [
        migrations.AddField(
            model_name="branderkundertoken",
            name="matrix_dm_since_token",
            field=models.CharField(max_length=500, blank=True),
        ),
    ]
