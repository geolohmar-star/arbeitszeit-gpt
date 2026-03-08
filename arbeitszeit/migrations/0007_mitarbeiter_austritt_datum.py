from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('arbeitszeit', '0029_seed_az_workflow'),
    ]

    operations = [
        migrations.AddField(
            model_name='mitarbeiter',
            name='austritt_datum',
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name='Austrittsdatum',
                help_text='Bei Setzen werden automatisch alle Zugaenge gesperrt.',
            ),
        ),
    ]
