from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("raumbuch", "0005_raum_matrix_jitsi_room_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="raum",
            name="hat_kundenkontakt",
            field=models.BooleanField(
                default=False,
                help_text="Stiller Alarm Button in Buchungsdetail anzeigen",
                verbose_name="Kundenkontakt-Raum",
            ),
        ),
    ]
