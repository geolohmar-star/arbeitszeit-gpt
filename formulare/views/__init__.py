# -*- coding: utf-8 -*-
"""formulare.views Package.

Re-exportiert alle oeffentlichen View-Funktionen die in urls.py referenziert werden.
Interne Hilfsfunktionen (Prefix '_') werden nicht re-exportiert.
"""

# Dashboard & Genehmigung
from .dashboard import (
    dashboard,
    meine_antraege,
    genehmigung_uebersicht,
    genehmigung_entscheiden,
)

# Aenderung Zeiterfassung
from .aenderung import (
    aenderung_zeiterfassung,
    aenderung_erfolg,
    aenderung_pdf,
    soll_fuer_datum,
    neue_tauschzeile,
    tausch_validierung,
    samstag_felder,
    neue_zeitzeile,
    aenderung_felder,
)

# Z-AG Antrag und Storno
from .zag import (
    zag_antrag,
    zag_erfolg,
    zag_pdf,
    zag_tage_zaehlen,
    neue_zag_zeile,
    zag_storno,
    zag_storno_erfolg,
    zag_storno_pdf,
    zag_storno_tage_zaehlen,
    neue_zag_storno_zeile,
)

# Zeitgutschrift
from .zeitgutschrift import (
    zeitgutschrift_antrag,
    zeitgutschrift_detail,
    zeitgutschrift_erfolg,
    zeitgutschrift_pdf,
    zeitgutschrift_felder,
    neue_zeitgutschrift_zeile,
    zeitgutschrift_fortbildung_berechnen,
    zeitgutschrift_erkrankung_berechnen,
    zeitgutschrift_datum_pruefen,
)

# Dienstreise
from .dienstreise import (
    dienstreise_erstellen,
    dienstreise_bearbeiten,
    dienstreise_uebersicht,
    meine_dienstreisen,
    dienstreise_detail,
    dienstreise_tagebuch_auswahl,
    dienstreise_tagebuch,
    dienstreise_tagebuch_eintrag_neu,
    dienstreise_tagebuch_eintrag_loeschen,
    dienstreise_gutschrift_beantragen,
    dienstreise_pdf,
)

# Anleitungen (PDF)
from .anleitung import anleitung_aenderung_pdf, anleitung_zeitgutschrift_pdf

# Team-Builder und API
from .team_builder import (
    api_team_queues,
    team_builder,
    team_builder_detail,
    team_builder_create,
    team_builder_update,
    team_builder_delete,
    team_builder_add_member,
    team_builder_remove_member,
)

# Hilfsfunktionen die von anderen Apps importiert werden koennen
from ._utils import (
    _sammle_workflow_unterzeichner,
    _signiere_pdf_alle_unterzeichner,
    _signiere_pdf_sicher,
)
# _erstelle_zag_eintraege wird von views_team_queue.py importiert
from .zag import _erstelle_zag_eintraege

__all__ = [
    # Dashboard
    "dashboard",
    "meine_antraege",
    "genehmigung_uebersicht",
    "genehmigung_entscheiden",
    # Aenderung
    "aenderung_zeiterfassung",
    "aenderung_erfolg",
    "aenderung_pdf",
    "soll_fuer_datum",
    "neue_tauschzeile",
    "tausch_validierung",
    "samstag_felder",
    "neue_zeitzeile",
    "aenderung_felder",
    # ZAG
    "zag_antrag",
    "zag_erfolg",
    "zag_pdf",
    "zag_tage_zaehlen",
    "neue_zag_zeile",
    "zag_storno",
    "zag_storno_erfolg",
    "zag_storno_pdf",
    "zag_storno_tage_zaehlen",
    "neue_zag_storno_zeile",
    # Zeitgutschrift
    "zeitgutschrift_antrag",
    "zeitgutschrift_detail",
    "zeitgutschrift_erfolg",
    "zeitgutschrift_pdf",
    "zeitgutschrift_felder",
    "neue_zeitgutschrift_zeile",
    "zeitgutschrift_fortbildung_berechnen",
    "zeitgutschrift_erkrankung_berechnen",
    "zeitgutschrift_datum_pruefen",
    # Dienstreise
    "dienstreise_erstellen",
    "dienstreise_bearbeiten",
    "dienstreise_uebersicht",
    "meine_dienstreisen",
    "dienstreise_detail",
    "dienstreise_tagebuch_auswahl",
    "dienstreise_tagebuch",
    "dienstreise_tagebuch_eintrag_neu",
    "dienstreise_tagebuch_eintrag_loeschen",
    "dienstreise_gutschrift_beantragen",
    "dienstreise_pdf",
    # Team-Builder
    "api_team_queues",
    "team_builder",
    "team_builder_detail",
    "team_builder_create",
    "team_builder_update",
    "team_builder_delete",
    "team_builder_add_member",
    "team_builder_remove_member",
    # Hilfsfunktionen (oeffentlich nutzbar)
    "_sammle_workflow_unterzeichner",
    "_signiere_pdf_alle_unterzeichner",
    "_signiere_pdf_sicher",
    "_erstelle_zag_eintraege",
]
