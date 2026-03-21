from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("formulare", "0026_fix_teamqueue_kuerzel_leer"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AntragsSignaturPDF",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("object_id", models.PositiveIntegerField()),
                ("signiertes_pdf", models.BinaryField()),
                ("aktualisiert_am", models.DateTimeField(auto_now=True)),
                ("anzahl_signaturen", models.PositiveSmallIntegerField(default=0)),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="signatur_pdfs",
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "zuletzt_signiert_von",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Antrags-Signatur-PDF",
                "verbose_name_plural": "Antrags-Signatur-PDFs",
                "unique_together": {("content_type", "object_id")},
            },
        ),
    ]
