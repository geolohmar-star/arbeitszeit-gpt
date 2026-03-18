from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr", "0010_dms_archiv_abteilung"),
    ]

    operations = [
        # Ersthelfer-Felder auf HRMitarbeiter
        migrations.AddField(
            model_name="hrmitarbeiter",
            name="ersthelfer_gueltig_bis",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Ersthelfer-Schein gueltig bis",
                help_text="Ablaufdatum des Erste-Hilfe-Scheins",
            ),
        ),
        migrations.AddField(
            model_name="hrmitarbeiter",
            name="ersthelfer_seit",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Ersthelfer seit",
                help_text="Datum der Ersthelfer-Ausbildung",
            ),
        ),
        migrations.AddField(
            model_name="hrmitarbeiter",
            name="ist_ersthelfer",
            field=models.BooleanField(
                default=False,
                verbose_name="Ist Ersthelfer/in",
                help_text="Diese Person ist ausgebildete Ersthelfer/in",
            ),
        ),
        # Betriebsarzt-Flag auf Stelle
        migrations.AddField(
            model_name="stelle",
            name="ist_betriebsarzt",
            field=models.BooleanField(
                default=False,
                verbose_name="Ist Betriebsarzt/Betriebsaerztin",
                help_text="Diese Stelle ist der Betriebsarzt / die Betriebsaerztin",
            ),
        ),
    ]
