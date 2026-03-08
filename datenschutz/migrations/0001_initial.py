import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Loeschprotokoll',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_id_intern', models.IntegerField(help_text='PK des geloeschten Django-Users – kein FK mehr.', verbose_name='Interne User-ID (war)')),
                ('personalnummer', models.CharField(max_length=20, verbose_name='Personalnummer')),
                ('nachname_kuerzel', models.CharField(help_text='Nur erste 3 Buchstaben – zur Identifikation bei Rueckfragen.', max_length=5, verbose_name='Nachname-Kuerzel (3 Zeichen)')),
                ('eintritt_datum', models.DateField(blank=True, null=True)),
                ('austritt_datum', models.DateField(blank=True, null=True)),
                ('loeschung_ausgefuehrt_am', models.DateTimeField(default=django.utils.timezone.now)),
                ('loeschung_durch', models.CharField(help_text="'System (pruefe_loeschfristen)' oder Username des Admins.", max_length=200, verbose_name='Ausgefuehrt durch')),
                ('kategorien', models.JSONField(default=dict, help_text='Dict: Kategoriename -> Anzahl Datensaetze.', verbose_name='Geloeschte Datenkategorien')),
                ('protokoll_pdf', models.BinaryField(blank=True, null=True, verbose_name='Protokoll-PDF')),
            ],
            options={
                'verbose_name': 'Loeschprotokoll',
                'verbose_name_plural': 'Loeschprotokolle',
                'ordering': ['-loeschung_ausgefuehrt_am'],
            },
        ),
    ]
