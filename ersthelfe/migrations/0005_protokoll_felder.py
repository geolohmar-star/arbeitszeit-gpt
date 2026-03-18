from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ersthelfe', '0004_alter_erstehilfeersthelfertoken_matrix_dm_room_id_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='erstehilfevorfall',
            name='protokoll_bewertung',
            field=models.CharField(
                blank=True,
                choices=[
                    ('positiv', 'Einsatz verlief problemlos'),
                    ('verbesserungsbedarf', 'Verbesserungsbedarf erkennbar'),
                    ('kritisch', 'Kritische Schwachstellen festgestellt'),
                ],
                max_length=30,
                verbose_name='Bewertung des Einsatzes',
            ),
        ),
        migrations.AddField(
            model_name='erstehilfevorfall',
            name='protokoll_erstellt_am',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Protokoll erstellt am'),
        ),
        migrations.AddField(
            model_name='erstehilfevorfall',
            name='protokoll_erstellt_von',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='eh_protokolle',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Protokoll erstellt von',
            ),
        ),
        migrations.AddField(
            model_name='erstehilfevorfall',
            name='protokoll_text',
            field=models.TextField(
                blank=True,
                help_text='Ergaenzungstext und Bewertung durch den Betriebsarzt',
                verbose_name='Protokolltext',
            ),
        ),
    ]
