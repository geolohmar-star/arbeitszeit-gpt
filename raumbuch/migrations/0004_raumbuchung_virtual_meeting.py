from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("raumbuch", "0003_jitsi_link_raumbuchung"),
    ]

    operations = [
        migrations.AddField(
            model_name="raumbuchung",
            name="virtual_meeting",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Kein virtuelles Meeting"),
                    ("jitsi", "Jitsi Meet (Video)"),
                    ("matrix", "Matrix/Element (Chat)"),
                ],
                default="",
                max_length=10,
                verbose_name="Virtuelles Meeting",
            ),
        ),
    ]
