from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("raumbuch", "0004_raumbuchung_virtual_meeting"),
    ]

    operations = [
        migrations.AddField(
            model_name="raum",
            name="matrix_room_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Direkte Element-URL, z.B. https://app.element.io/#/room/!ID:georg-klein.com",
                verbose_name="Matrix-Raum-URL",
            ),
        ),
        migrations.AddField(
            model_name="raum",
            name="jitsi_room_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Fester Jitsi-Meeting-Link fuer diesen Raum (optional). Ueberschreibt den automatisch generierten Link.",
                verbose_name="Jitsi-Raum-URL",
            ),
        ),
    ]
