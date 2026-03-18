from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dms", "0009_add_workflow_instance"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="dokument",
            name="loeschen_am",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Loeschen am",
                help_text="Geplantes Loeschdatum (nur wirksam nach DSB-Freigabe).",
            ),
        ),
        migrations.AddField(
            model_name="dokument",
            name="loeschen_begruendung",
            field=models.TextField(blank=True, verbose_name="Loeschbegruendung"),
        ),
        migrations.AddField(
            model_name="dokument",
            name="loeschen_beantragt_von",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="dms_loeschantraege",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Loeschantrag von",
            ),
        ),
        migrations.AddField(
            model_name="dokument",
            name="loeschen_genehmigt",
            field=models.BooleanField(default=False, verbose_name="Loeschung genehmigt"),
        ),
    ]
