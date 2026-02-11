from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('arbeitszeit', '0014_mitarbeiter_telefon_alter_mitarbeiter_verfuegbarkeit'),
        ('schichtplan', '0008_schicht_ersatz_markierung_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='SchichtplanSnapshot',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('schichtplan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='snapshots', to='schichtplan.schichtplan')),
                ('erstellt_von', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Schichtplan-Snapshot',
                'verbose_name_plural': 'Schichtplan-Snapshots',
                'ordering': ['-erstellt_am'],
            },
        ),
        migrations.CreateModel(
            name='SchichtplanSnapshotSchicht',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datum', models.DateField()),
                ('mitarbeiter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='arbeitszeit.mitarbeiter')),
                ('schichttyp', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='schichtplan.schichttyp')),
                ('snapshot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schichten', to='schichtplan.schichtplansnapshot')),
            ],
            options={
                'verbose_name': 'Snapshot-Schicht',
                'verbose_name_plural': 'Snapshot-Schichten',
                'ordering': ['datum', 'schichttyp__start_zeit'],
            },
        ),
    ]
