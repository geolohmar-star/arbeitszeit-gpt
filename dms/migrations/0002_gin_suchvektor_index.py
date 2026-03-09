"""
Migration 0002: GIN-Index auf suchvektor fuer PostgreSQL-Volltext-Suche.

Wird nur auf PostgreSQL-Datenbanken ausgefuehrt (SQLite-Schutz via connection.vendor-Pruefung).
"""
from django.db import migrations


def gin_index_erstellen(apps, schema_editor):
    """Erstellt den GIN-Index direkt per SQL (nur PostgreSQL)."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS dms_dokument_suchvektor_gin "
        "ON dms_dokument USING GIN (to_tsvector('german', COALESCE(titel,'') || ' ' || COALESCE(beschreibung,'')))"
    )


def gin_index_loeschen(apps, schema_editor):
    """Loescht den GIN-Index (nur PostgreSQL)."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP INDEX IF EXISTS dms_dokument_suchvektor_gin"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("dms", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            gin_index_erstellen,
            gin_index_loeschen,
        ),
    ]
