"""Einstellungs-Service: Bewerbung --> HRMitarbeiter + Personalstammdaten.

Wird aufgerufen wenn HR einen Bewerber einstellt.
Erstellt automatisch: Django-User, HRMitarbeiter, Personalstammdaten.
Uebertraegt Dokumente in die verschluesselte dokumente-App.
Loescht anschliessend alle Bewerbungs-Rohdaten (DSGVO-Hard-Delete).
"""
import logging

from django.contrib.auth.models import User
from django.db import transaction

logger = logging.getLogger(__name__)


def _generiere_username(vorname: str, nachname: str) -> str:
    """Erstellt einen eindeutigen Username aus Vor- und Nachname."""
    import re
    basis = f"{vorname.lower()}.{nachname.lower()}"
    basis = re.sub(r"[^a-z0-9.]", "", basis.replace(" ", "."))
    username = basis
    zaehler = 1
    while User.objects.filter(username=username).exists():
        username = f"{basis}.{zaehler}"
        zaehler += 1
    return username


@transaction.atomic
def stelle_ein(bewerbung, stelle=None, eintrittsdatum=None, erstellt_von=None):
    """Stellt einen Bewerber ein.

    1. Django-User anlegen
    2. HRMitarbeiter anlegen (aus Bewerbungsdaten)
    3. Personalstammdaten anlegen (aus Bewerbungsdaten)
    4. Dokumente verschluesselt in dokumente-App uebertragen
    5. Bewerbungs-Rohdaten loeschen (DSGVO)

    Returns:
        hr.HRMitarbeiter – der neu angelegte Mitarbeiter
    """
    from hr.models import HRMitarbeiter, Personalstammdaten
    from dokumente.models import SensiblesDokument
    from dokumente.services import entschluessel_dokument, verschluessel_dokument

    # 1. Django-User erstellen
    username = _generiere_username(bewerbung.vorname, bewerbung.nachname)
    user = User.objects.create_user(
        username=username,
        first_name=bewerbung.vorname,
        last_name=bewerbung.nachname,
        email=bewerbung.email_privat or "",
    )
    logger.info("Einstellung: User '%s' erstellt.", username)

    # 2. HRMitarbeiter erstellen
    hr_ma = HRMitarbeiter.objects.create(
        user=user,
        vorname=bewerbung.vorname,
        nachname=bewerbung.nachname,
        stelle=stelle or bewerbung.angestrebte_stelle,
        eintrittsdatum=eintrittsdatum or bewerbung.geplantes_eintrittsdatum,
        email=bewerbung.email_privat or "",
    )
    logger.info("Einstellung: HRMitarbeiter '%s' (PNr: %s) erstellt.", hr_ma.vollname, hr_ma.personalnummer)

    # 3. Personalstammdaten erstellen (alle sensiblen Felder aus Bewerbung)
    Personalstammdaten.objects.create(
        mitarbeiter=hr_ma,
        angelegt_von=erstellt_von,
        anrede=bewerbung.anrede,
        geburtsdatum=bewerbung.geburtsdatum,
        geburtsort=bewerbung.geburtsort,
        geburtsname=bewerbung.geburtsname,
        staatsangehoerigkeit=bewerbung.staatsangehoerigkeit,
        familienstand=bewerbung.familienstand,
        konfession=bewerbung.konfession,
        anzahl_kinder=bewerbung.anzahl_kinder,
        strasse=bewerbung.strasse,
        hausnummer=bewerbung.hausnummer,
        plz=bewerbung.plz,
        ort=bewerbung.ort,
        land=bewerbung.land,
        telefon_privat=bewerbung.telefon_privat,
        mobil_privat=bewerbung.mobil_privat,
        email_privat=bewerbung.email_privat,
        steuerklasse=bewerbung.steuerklasse,
        steuer_id=bewerbung.steuer_id,
        sozialversicherungsnummer=bewerbung.sozialversicherungsnummer,
        iban=bewerbung.iban,
        bic=bewerbung.bic,
        bank_name=bewerbung.bank_name,
        krankenkasse_name=bewerbung.krankenkasse_name,
        krankenversicherungsart=bewerbung.krankenversicherungsart,
        notfallkontakt_name=bewerbung.notfallkontakt_name,
        notfallkontakt_beziehung=bewerbung.notfallkontakt_beziehung,
        notfallkontakt_telefon=bewerbung.notfallkontakt_telefon,
        vertragsart=bewerbung.vertragsart,
        probezeit_bis=bewerbung.probezeit_bis,
    )
    logger.info("Einstellung: Personalstammdaten fuer '%s' angelegt.", hr_ma.vollname)

    # 4. Bewerbungsdokumente in dokumente-App uebertragen (neu verschluesseln)
    kat_map = {
        "ausweis": "ausweis",
        "zeugnis_schule": "zeugnis",
        "zeugnis_arbeit": "zeugnis",
        "abschluss": "abschluss",
        "fuehrerschein": "ausweis",
        "sonstige": "sonstige",
    }
    for bdok in bewerbung.dokumente.all():
        try:
            inhalt_roh = entschluessel_dokument(bdok.inhalt_verschluesselt)
            inhalt_neu = verschluessel_dokument(inhalt_roh)
            SensiblesDokument.objects.create(
                user=user,
                hochgeladen_von=erstellt_von,
                kategorie=kat_map.get(bdok.typ, "sonstige"),
                dateiname=bdok.dateiname,
                dateityp=bdok.dateityp,
                inhalt_verschluesselt=inhalt_neu,
                groesse_bytes=bdok.groesse_bytes,
                beschreibung=f"Aus Bewerbung uebernommen ({bdok.get_typ_display()})",
            )
        except Exception as exc:
            logger.error("Dokument-Uebertragung fehlgeschlagen ('%s'): %s", bdok.dateiname, exc)

    logger.info("Einstellung: %d Dokument(e) uebertragen.", bewerbung.dokumente.count())

    # 5. Bewerbungs-Rohdaten loeschen (DSGVO Hard-Delete)
    bewerbung_name = bewerbung.vollname
    bewerbung.delete()
    logger.info("Einstellung abgeschlossen: Bewerbungsdaten '%s' geloescht (DSGVO).", bewerbung_name)

    return hr_ma


@transaction.atomic
def lehne_ab(bewerbung, abgelehnt_von=None):
    """Lehnt eine Bewerbung ab und loescht ALLE Daten unwiederbringlich (DSGVO).

    Kein Soft-Delete, kein Archiv – vollstaendige Vernichtung.
    """
    name = bewerbung.vollname
    bewerbung.delete()  # CASCADE loescht auch BewerbungDokument
    logger.info(
        "Bewerbung abgelehnt und DSGVO-konform geloescht: '%s' (abgelehnt von: %s).",
        name,
        abgelehnt_von.username if abgelehnt_von else "unbekannt",
    )
