from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr", "0011_ersthelfer_betriebsarzt"),
    ]

    operations = [
        migrations.AddField(
            model_name="hrmitarbeiter",
            name="ist_brandbekaempfer",
            field=models.BooleanField(
                default=False,
                help_text="Erste-Loesch-Versuch bis Feuerwehr eintrifft",
                verbose_name="Ist Brandbekaempfer/in",
            ),
        ),
        migrations.AddField(
            model_name="hrmitarbeiter",
            name="ist_branderkunder",
            field=models.BooleanField(
                default=False,
                help_text="Erkundet gemeldeten Brandort und bestaetigt oder verneint",
                verbose_name="Ist Branderkunder/in",
            ),
        ),
        migrations.AddField(
            model_name="hrmitarbeiter",
            name="ist_raeumungshelfer",
            field=models.BooleanField(
                default=False,
                help_text="Unterstuetzt die Evakuierung des Gebaeudes",
                verbose_name="Ist Raeumungshelfer/in",
            ),
        ),
    ]
