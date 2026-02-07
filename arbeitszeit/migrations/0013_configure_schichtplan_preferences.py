# Generated data migration

from django.db import migrations


def configure_schichtplan_preferences(apps, schema_editor):
    """
    Konfiguriert die Schichtplan-Präferenzen für bestehende Mitarbeiter
    basierend auf der Schichtplan-Analyse.
    """
    Mitarbeiter = apps.get_model('arbeitszeit', 'Mitarbeiter')
    
    for ma in Mitarbeiter.objects.all():
        kennung = ma.schichtplan_kennung
        
        # MA1: Mittwochskraft
        if kennung == 'MA1':
            ma.kategorie = 'kern'
            ma.fixe_tag_wochentage = [2]  # Mittwoch (0=Mo, 2=Mi)
            ma.zaehlt_zur_tagbesetzung = True
            ma.zaehlt_zur_nachtbesetzung = False
            ma.target_tagschichten_pro_monat = 4  # Ca. 3-4 pro Monat
            ma.target_nachtschichten_pro_monat = 0
        
        # MA7: Hybrid-Rolle
        elif kennung == 'MA7':
            ma.kategorie = 'hybrid'
            ma.fixe_tag_wochentage = [1, 3]  # Dienstag, Donnerstag
            ma.zaehlt_zur_tagbesetzung = False  # Tagdienste ZUSÄTZLICH
            ma.zaehlt_zur_nachtbesetzung = True  # Nachtdienste REGULÄR
            ma.wochenend_nachtdienst_block = True  # Immer Fr-Sa oder Sa-So
            ma.nachtschicht_nur_wochenende = True  # Nur Wochenende
            ma.target_tagschichten_pro_monat = 7  # Ca. 6-7 pro Monat (zusätzlich)
            ma.target_nachtschichten_pro_monat = 5  # Ca. 4-5 pro Monat
        
        # MA3: Dauerkrank
        elif kennung == 'MA3':
            ma.kategorie = 'dauerkrank'
            ma.aktiv = False
            ma.zaehlt_zur_tagbesetzung = False
            ma.zaehlt_zur_nachtbesetzung = False
        
        # MA12: Zusatzkraft
        elif kennung == 'MA12':
            ma.kategorie = 'zusatz'
            ma.zaehlt_zur_tagbesetzung = False
            ma.zaehlt_zur_nachtbesetzung = False
            ma.nur_zusatzarbeiten = True
        
        # Alle anderen: Kernteam (MA2, MA4, MA5, MA8, MA9, MA10, MA11, MA13, MA14, MA15)
        else:
            ma.kategorie = 'kern'
            ma.zaehlt_zur_tagbesetzung = True
            ma.zaehlt_zur_nachtbesetzung = True
            ma.target_tagschichten_pro_monat = 6  # 5-6 pro Monat
            ma.target_nachtschichten_pro_monat = 5  # 5-6 pro Monat
            
            # Typ B: Min. 4T + 4N
            if ma.schicht_typ == 'typ_b':
                ma.min_tagschichten_pro_monat = 4
                ma.min_nachtschichten_pro_monat = 4
        
        ma.save()


def reverse_configure(apps, schema_editor):
    """Rückgängig machen - setzt Felder auf Defaults zurück"""
    Mitarbeiter = apps.get_model('arbeitszeit', 'Mitarbeiter')
    
    for ma in Mitarbeiter.objects.all():
        ma.kategorie = 'kern'
        ma.fixe_tag_wochentage = None
        ma.zaehlt_zur_tagbesetzung = True
        ma.zaehlt_zur_nachtbesetzung = True
        ma.wochenend_nachtdienst_block = False
        ma.min_tagschichten_pro_monat = None
        ma.min_nachtschichten_pro_monat = None
        ma.target_tagschichten_pro_monat = 6
        ma.target_nachtschichten_pro_monat = 5
        ma.save()


class Migration(migrations.Migration):

    dependencies = [
        ('arbeitszeit', '0012_mitarbeiter_fixe_tag_wochentage_and_more'),
    ]

    operations = [
        migrations.RunPython(
            configure_schichtplan_preferences,
            reverse_code=reverse_configure
        ),
    ]
