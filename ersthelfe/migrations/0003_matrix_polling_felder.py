from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ersthelfe", "0002_alter_erstehilfevorfall_ort"),
    ]

    operations = [
        migrations.AddField(
            model_name="erstehilfevorfall",
            name="matrix_ping_event_id",
            field=models.CharField(blank=True, max_length=200, verbose_name="Matrix EH_PING Event-ID"),
        ),
        migrations.AddField(
            model_name="erstehilfevorfall",
            name="matrix_ping_since_token",
            field=models.CharField(blank=True, max_length=500, verbose_name="Matrix EH_PING Since-Token"),
        ),
        migrations.AddField(
            model_name="erstehilfeersthelfertoken",
            name="matrix_dm_room_id",
            field=models.CharField(blank=True, max_length=200, verbose_name="Matrix-DM-Raum-ID"),
        ),
        migrations.AddField(
            model_name="erstehilfeersthelfertoken",
            name="matrix_dm_since_token",
            field=models.CharField(blank=True, max_length=500, verbose_name="Matrix-DM Since-Token"),
        ),
    ]
