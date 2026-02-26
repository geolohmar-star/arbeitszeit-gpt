# Migration: Standort-Modell einfuehren und Mitarbeiter.standort migrieren.
#
# Reihenfolge:
#   1. Standort-Tabelle erstellen (CharField-basiertes Modell)
#   2. Standort-Objekte anlegen (NRW fuer Siegburg + Bonn)
#   3. Neues nullable FK-Feld standort_ref hinzufuegen
#   4. Mitarbeiter anhand altem standort-String verknuepfen
#   5. Altes standort-CharField entfernen
#   6. standort_ref -> standort umbenennen

import django.db.models.deletion
from django.db import migrations, models

INITIALE_STANDORTE = [
    {"kuerzel": "siegburg", "name": "Siegburg", "plz": "53721", "bundesland": "NW"},
    {"kuerzel": "bonn",     "name": "Bonn",     "plz": "53111", "bundesland": "NW"},
]

BUNDESLAND_CHOICES = [
    ("BW", "Baden-Wuerttemberg"), ("BY", "Bayern"), ("BE", "Berlin"),
    ("BB", "Brandenburg"), ("HB", "Bremen"), ("HH", "Hamburg"),
    ("HE", "Hessen"), ("MV", "Mecklenburg-Vorpommern"), ("NI", "Niedersachsen"),
    ("NW", "Nordrhein-Westfalen"), ("RP", "Rheinland-Pfalz"), ("SL", "Saarland"),
    ("SN", "Sachsen"), ("ST", "Sachsen-Anhalt"), ("SH", "Schleswig-Holstein"),
    ("TH", "Thueringen"),
]


def erstelle_standorte_und_verknuepfe(apps, schema_editor):
    """Standort-Objekte anlegen und Mitarbeiter per standort_ref verknuepfen."""
    Standort = apps.get_model("arbeitszeit", "Standort")
    Mitarbeiter = apps.get_model("arbeitszeit", "Mitarbeiter")

    # Standorte anlegen
    for daten in INITIALE_STANDORTE:
        Standort.objects.get_or_create(kuerzel=daten["kuerzel"], defaults=daten)

    # Mitarbeiter verknuepfen: altes standort-Textfeld -> neues standort_ref FK
    # (Der alte Wert steckt noch im CharField 'standort')
    for ma in Mitarbeiter.objects.all():
        try:
            standort_obj = Standort.objects.get(kuerzel=ma.standort)
            ma.standort_ref = standort_obj
            ma.save()
        except Standort.DoesNotExist:
            # Kein passender Standort: FK bleibt None (nullable)
            pass


def rueckwaerts(apps, schema_editor):
    """Rueckwaerts: Mitarbeiter bekommen alten standort-String zurueck."""
    Mitarbeiter = apps.get_model("arbeitszeit", "Mitarbeiter")
    for ma in Mitarbeiter.objects.select_related("standort_ref").all():
        if ma.standort_ref:
            ma.standort = ma.standort_ref.kuerzel
            ma.save()


class Migration(migrations.Migration):

    dependencies = [
        ('arbeitszeit', '0026_vorgesetzter_feld'),
    ]

    operations = [
        # Schritt 1: Standort-Tabelle erstellen
        migrations.CreateModel(
            name='Standort',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                )),
                ('kuerzel', models.CharField(
                    max_length=20, unique=True, verbose_name='Kuerzel',
                    help_text="Internes Kuerzel, z.B. 'siegburg'",
                )),
                ('name', models.CharField(
                    max_length=100, verbose_name='Name',
                )),
                ('plz', models.CharField(
                    max_length=5, verbose_name='PLZ',
                    help_text='Postleitzahl des Standorts (5-stellig)',
                )),
                ('bundesland', models.CharField(
                    max_length=2, choices=BUNDESLAND_CHOICES,
                    verbose_name='Bundesland',
                    help_text='Bestimmt den Feiertagskalender',
                )),
            ],
            options={
                'verbose_name': 'Standort',
                'verbose_name_plural': 'Standorte',
                'ordering': ['name'],
            },
        ),

        # Schritt 2: Neues FK-Feld hinzufuegen (nullable, temporaer)
        migrations.AddField(
            model_name='mitarbeiter',
            name='standort_ref',
            field=models.ForeignKey(
                to='arbeitszeit.Standort',
                on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True,
                verbose_name='Standort',
            ),
        ),

        # Schritt 3: Standorte anlegen + Mitarbeiter verknuepfen
        migrations.RunPython(
            erstelle_standorte_und_verknuepfe,
            rueckwaerts,
        ),

        # Schritt 4: Altes CharField entfernen
        migrations.RemoveField(
            model_name='mitarbeiter',
            name='standort',
        ),

        # Schritt 5: standort_ref -> standort umbenennen
        migrations.RenameField(
            model_name='mitarbeiter',
            old_name='standort_ref',
            new_name='standort',
        ),
    ]
