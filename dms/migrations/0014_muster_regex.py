"""Migration: OCR-Text-Muster-Typ und muster_regex-Feld fuer PaperlessWorkflowRegel."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dms", "0013_alter_zugriffsprotokoll_aktion_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="paperlessworkflowregel",
            name="muster_regex",
            field=models.CharField(
                blank=True,
                max_length=500,
                verbose_name="Regulaerer Ausdruck (Muster)",
                help_text=(
                    "Python-kompatibler regulaerer Ausdruck der im OCR-Text gesucht wird. "
                    "Beispiel: [A-Z]{2,6}-\\d{3,6}-\\d{6}  erkennt Aktenzeichen wie AES-234-023. "
                    "Nur benoetigt bei Treffer-Typ 'OCR-Text-Muster'."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="paperlessworkflowregel",
            name="paperless_name",
            field=models.CharField(
                blank=True,
                max_length=200,
                verbose_name="Paperless-Name",
                help_text=(
                    "Name des Dokumenttyps oder Tags in Paperless-ngx (Gross/Kleinschreibung egal). "
                    "Nicht benoetigt bei Treffer-Typ 'Muster'."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="paperlessworkflowregel",
            name="treffer_typ",
            field=models.CharField(
                choices=[
                    ("dokumenttyp", "Paperless Dokumenttyp (Name)"),
                    ("tag", "Paperless Tag (Name)"),
                    ("muster", "OCR-Text-Muster (Regulaerer Ausdruck)"),
                ],
                default="dokumenttyp",
                max_length=20,
                verbose_name="Treffer-Typ",
            ),
        ),
    ]
