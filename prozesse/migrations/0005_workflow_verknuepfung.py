"""Migration: workflow_template an FormularSchema + workflow_instance an FormularEintrag."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prozesse", "0004_vorgangsnummer_kuerzel"),
        ("workflow", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="formularschema",
            name="workflow_template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="formular_schemata",
                to="workflow.workflowtemplate",
                verbose_name="Workflow bei Eingang",
            ),
        ),
        migrations.AddField(
            model_name="formulareintrag",
            name="workflow_instance",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="formular_eintrag",
                to="workflow.workflowinstance",
                verbose_name="Workflow-Instanz",
            ),
        ),
    ]
