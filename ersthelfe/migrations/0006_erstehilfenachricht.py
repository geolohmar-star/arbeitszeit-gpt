from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ersthelfe', '0005_protokoll_felder'),
        ('hr', '0011_ersthelfer_betriebsarzt'),
    ]

    operations = [
        migrations.CreateModel(
            name='ErsteHilfeNachricht',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('absender_matrix_id', models.CharField(blank=True, max_length=200, verbose_name='Matrix-ID (Fallback)')),
                ('gesendet_am', models.DateTimeField(auto_now_add=True)),
                ('text', models.TextField(verbose_name='Nachricht')),
                ('absender', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='eh_nachrichten',
                    to='hr.hrmitarbeiter',
                    verbose_name='Absender',
                )),
                ('vorfall', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='nachrichten',
                    to='ersthelfe.erstehilfevorfall',
                    verbose_name='Vorfall',
                )),
            ],
            options={
                'verbose_name': 'EH-Nachricht',
                'verbose_name_plural': 'EH-Nachrichten',
                'ordering': ['gesendet_am'],
            },
        ),
    ]
