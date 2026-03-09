"""DMS REST-API fuer externe Systeme (SAP, Paperless-ngx, etc.).

Authentifizierung: Bearer-Token im Authorization-Header
    Authorization: Bearer <64-stelliger Hex-Token>

Alle Endpunkte liegen unter /dms/api/v1/ und geben JSON zurueck.
Fehlerantworten folgen dem Format: {"fehler": "Beschreibung", "code": "FEHLERCODE"}
"""
import json
import logging
from datetime import timedelta
from functools import wraps

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import ApiToken, Dokument, DokumentKategorie, DokumentVersion, ZugriffsProtokoll
from .services import lade_dokument, speichere_dokument

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API-Version
# ---------------------------------------------------------------------------
API_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Authentifizierung
# ---------------------------------------------------------------------------

def _token_aus_request(request):
    """Liest den Bearer-Token aus dem Authorization-Header."""
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def _pruefe_token(request):
    """Prueft den API-Token und gibt das ApiToken-Objekt zurueck oder None."""
    token_wert = _token_aus_request(request)
    if not token_wert:
        return None
    try:
        api_token = ApiToken.objects.get(token=token_wert, aktiv=True)
        # Letzte Nutzung aktualisieren (max. einmal pro Minute schreiben)
        jetzt = timezone.now()
        if not api_token.letzte_nutzung or (jetzt - api_token.letzte_nutzung) > timedelta(minutes=1):
            ApiToken.objects.filter(pk=api_token.pk).update(letzte_nutzung=jetzt)
        return api_token
    except ApiToken.DoesNotExist:
        return None


def api_auth_required(view_func):
    """Decorator: prueft Bearer-Token, gibt 401 zurueck wenn ungueltig."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        api_token = _pruefe_token(request)
        if api_token is None:
            return JsonResponse(
                {"fehler": "Authentifizierung erforderlich. Bearer-Token fehlt oder ungueltig.", "code": "UNAUTHORIZED"},
                status=401,
            )
        request.api_token = api_token
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _get_ip(request):
    ip = request.META.get("HTTP_X_FORWARDED_FOR")
    if ip:
        return ip.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _protokolliere_api(request, dokument, aktion, notiz=""):
    ZugriffsProtokoll.objects.create(
        dokument=dokument,
        user=None,
        aktion=aktion,
        ip_adresse=_get_ip(request),
        notiz=f"[{request.api_token.bezeichnung}] {notiz}".strip(),
    )


def _dokument_zu_dict(dok):
    """Serialisiert ein Dokument-Objekt als JSON-kompatibles Dict."""
    return {
        "id": dok.pk,
        "titel": dok.titel,
        "dateiname": dok.dateiname,
        "dateityp": dok.dateityp,
        "groesse_bytes": dok.groesse_bytes,
        "klasse": dok.klasse,
        "version": dok.version,
        "kategorie": str(dok.kategorie) if dok.kategorie else None,
        "kategorie_id": dok.kategorie_id,
        "beschreibung": dok.beschreibung,
        "gueltig_bis": dok.gueltig_bis.isoformat() if dok.gueltig_bis else None,
        "erstellt_am": dok.erstellt_am.isoformat(),
        "paperless_id": dok.paperless_id,
        "tags": [t.name for t in dok.tags.all()],
    }


# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------

@csrf_exempt
@api_auth_required
@require_http_methods(["GET"])
def api_health(request):
    """GET /dms/api/v1/health/
    Verbindungstest. Gibt API-Version und Token-Bezeichnung zurueck.
    """
    return JsonResponse({
        "status": "ok",
        "api_version": API_VERSION,
        "system": request.api_token.bezeichnung,
        "zeitpunkt": timezone.now().isoformat(),
    })


@csrf_exempt
@api_auth_required
@require_http_methods(["GET", "POST"])
def api_dokumente(request):
    """GET/POST /dms/api/v1/dokumente/

    GET: Dokumentenliste abrufen.
        Query-Parameter:
            klasse      = offen | sensibel
            kategorie   = Kategorie-ID (Integer)
            suche       = Freitext (durchsucht Titel + Dateiname)
            limit       = Anzahl Ergebnisse (Standard: 50, max: 200)
            offset      = Offset fuer Paginierung (Standard: 0)

    POST: Neues Dokument hochladen (multipart/form-data).
        Felder:
            datei       = Datei-Inhalt (required)
            titel       = Dokumententitel (required)
            klasse      = offen | sensibel (Standard: offen)
            kategorie   = Kategorie-ID (optional)
            beschreibung= Freitext (optional)
            gueltig_bis = Datum ISO 8601 (optional, z.B. 2027-12-31)
            kommentar   = Versionkommentar (optional)
    """
    if request.method == "GET":
        return _api_dokumente_liste(request)
    return _api_dokument_upload(request)


def _api_dokumente_liste(request):
    """Dokumentenliste mit Filterung und Paginierung."""
    qs = Dokument.objects.all()

    # Klassen-Einschraenkung durch Token-Berechtigung
    if request.api_token.erlaubte_klassen == "offen":
        qs = qs.filter(klasse="offen")

    # Filter aus Query-Parametern
    klasse = request.GET.get("klasse")
    if klasse in ("offen", "sensibel"):
        # Sensibel nur wenn Token das erlaubt
        if klasse == "sensibel" and request.api_token.erlaubte_klassen != "beide":
            return JsonResponse(
                {"fehler": "Dieser Token hat keinen Zugriff auf sensible Dokumente.", "code": "FORBIDDEN"},
                status=403,
            )
        qs = qs.filter(klasse=klasse)

    kategorie_id = request.GET.get("kategorie")
    if kategorie_id:
        qs = qs.filter(kategorie_id=kategorie_id)

    suche = request.GET.get("suche", "").strip()
    if suche:
        from django.db.models import Q
        qs = qs.filter(Q(titel__icontains=suche) | Q(dateiname__icontains=suche))

    try:
        limit = min(int(request.GET.get("limit", 50)), 200)
        offset = int(request.GET.get("offset", 0))
    except ValueError:
        return JsonResponse({"fehler": "limit und offset muessen Ganzzahlen sein.", "code": "BAD_REQUEST"}, status=400)

    gesamt = qs.count()
    dokumente = qs.select_related("kategorie")[offset:offset + limit]

    return JsonResponse({
        "gesamt": gesamt,
        "limit": limit,
        "offset": offset,
        "dokumente": [_dokument_zu_dict(d) for d in dokumente],
    })


def _api_dokument_upload(request):
    """Neues Dokument via API hochladen."""
    if "datei" not in request.FILES:
        return JsonResponse({"fehler": "Feld 'datei' fehlt.", "code": "BAD_REQUEST"}, status=400)

    titel = request.POST.get("titel", "").strip()
    if not titel:
        return JsonResponse({"fehler": "Feld 'titel' fehlt.", "code": "BAD_REQUEST"}, status=400)

    klasse = request.POST.get("klasse", "offen")
    if klasse not in ("offen", "sensibel"):
        return JsonResponse({"fehler": "klasse muss 'offen' oder 'sensibel' sein.", "code": "BAD_REQUEST"}, status=400)

    if klasse == "sensibel" and request.api_token.erlaubte_klassen != "beide":
        return JsonResponse(
            {"fehler": "Dieser Token darf keine sensiblen Dokumente hochladen.", "code": "FORBIDDEN"},
            status=403,
        )

    datei = request.FILES["datei"]
    inhalt = datei.read()

    # Kategorie aufloesen
    kategorie = None
    kategorie_id = request.POST.get("kategorie")
    if kategorie_id:
        try:
            kategorie = DokumentKategorie.objects.get(pk=int(kategorie_id))
        except (DokumentKategorie.DoesNotExist, ValueError):
            return JsonResponse({"fehler": f"Kategorie {kategorie_id} nicht gefunden.", "code": "NOT_FOUND"}, status=404)

    # Ablaufdatum
    gueltig_bis = None
    gueltig_bis_str = request.POST.get("gueltig_bis", "")
    if gueltig_bis_str:
        try:
            from datetime import date
            gueltig_bis = date.fromisoformat(gueltig_bis_str)
        except ValueError:
            return JsonResponse({"fehler": "gueltig_bis muss ISO-8601-Datum sein (z.B. 2027-12-31).", "code": "BAD_REQUEST"}, status=400)

    import mimetypes
    mime = datei.content_type or mimetypes.guess_type(datei.name)[0] or "application/octet-stream"

    dok = Dokument(
        titel=titel,
        dateiname=datei.name,
        dateityp=mime,
        groesse_bytes=len(inhalt),
        klasse=klasse,
        kategorie=kategorie,
        beschreibung=request.POST.get("beschreibung", ""),
        gueltig_bis=gueltig_bis,
        version=1,
    )

    speichere_dokument(dok, inhalt)

    # Erste Version protokollieren
    kommentar = request.POST.get("kommentar", f"API-Upload durch {request.api_token.bezeichnung}")
    DokumentVersion.objects.create(
        dokument=dok,
        version_nr=1,
        dateiname=datei.name,
        inhalt_roh=dok.inhalt_roh,
        inhalt_verschluesselt=dok.inhalt_verschluesselt,
        verschluessel_nonce=dok.verschluessel_nonce,
        groesse_bytes=len(inhalt),
        kommentar=kommentar,
    )

    _protokolliere_api(request, dok, "api_upload", f"Datei: {datei.name}, Groesse: {len(inhalt)} Bytes")
    logger.info("DMS API-Upload: Dokument %s (pk=%d) durch Token '%s'", titel, dok.pk, request.api_token.bezeichnung)

    return JsonResponse(_dokument_zu_dict(dok), status=201)


@csrf_exempt
@api_auth_required
@require_http_methods(["GET"])
def api_dokument_detail(request, pk):
    """GET /dms/api/v1/dokumente/{pk}/
    Metadaten eines einzelnen Dokuments abrufen.
    """
    try:
        dok = Dokument.objects.select_related("kategorie").get(pk=pk)
    except Dokument.DoesNotExist:
        return JsonResponse({"fehler": f"Dokument {pk} nicht gefunden.", "code": "NOT_FOUND"}, status=404)

    if dok.klasse == "sensibel" and request.api_token.erlaubte_klassen != "beide":
        return JsonResponse({"fehler": "Keine Berechtigung fuer sensible Dokumente.", "code": "FORBIDDEN"}, status=403)

    data = _dokument_zu_dict(dok)
    # Versionen als Ueberblick mitliefern
    data["versionen"] = list(
        dok.versionen.values("version_nr", "erstellt_am", "groesse_bytes", "kommentar")
    )
    return JsonResponse(data)


@csrf_exempt
@api_auth_required
@require_http_methods(["GET"])
def api_dokument_inhalt(request, pk):
    """GET /dms/api/v1/dokumente/{pk}/inhalt/
    Rohen Dateiinhalt als Binaer-Download zurueckgeben.
    Content-Type entspricht dem MIME-Typ des Dokuments.
    """
    try:
        dok = Dokument.objects.get(pk=pk)
    except Dokument.DoesNotExist:
        return JsonResponse({"fehler": f"Dokument {pk} nicht gefunden.", "code": "NOT_FOUND"}, status=404)

    if dok.klasse == "sensibel" and request.api_token.erlaubte_klassen != "beide":
        return JsonResponse({"fehler": "Keine Berechtigung fuer sensible Dokumente.", "code": "FORBIDDEN"}, status=403)

    inhalt = lade_dokument(dok)
    _protokolliere_api(request, dok, "api_download", f"Dokument-ID {pk}")

    response = HttpResponse(inhalt, content_type=dok.dateityp or "application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{dok.dateiname}"'
    response["X-PRIMA-Dokument-ID"] = str(dok.pk)
    response["X-PRIMA-Version"] = str(dok.version)
    return response


@csrf_exempt
@api_auth_required
@require_http_methods(["POST"])
def api_dokument_neue_version(request, pk):
    """POST /dms/api/v1/dokumente/{pk}/version/
    Neue Version eines bestehenden Dokuments hochladen.
    Felder identisch mit dem Upload-Endpunkt, jedoch ohne titel/klasse.
    Optional: kommentar (Versionsbeschreibung)
    """
    try:
        dok = Dokument.objects.get(pk=pk)
    except Dokument.DoesNotExist:
        return JsonResponse({"fehler": f"Dokument {pk} nicht gefunden.", "code": "NOT_FOUND"}, status=404)

    if dok.klasse == "sensibel" and request.api_token.erlaubte_klassen != "beide":
        return JsonResponse({"fehler": "Keine Berechtigung fuer sensible Dokumente.", "code": "FORBIDDEN"}, status=403)

    if "datei" not in request.FILES:
        return JsonResponse({"fehler": "Feld 'datei' fehlt.", "code": "BAD_REQUEST"}, status=400)

    datei = request.FILES["datei"]
    inhalt = datei.read()

    # Alten Inhalt als neue Version sichern (vorherige Version archivieren)
    neue_version_nr = dok.version + 1
    speichere_dokument(dok, inhalt)
    dok.dateiname = datei.name
    dok.groesse_bytes = len(inhalt)
    dok.version = neue_version_nr
    dok.save()

    kommentar = request.POST.get("kommentar", f"API-Version durch {request.api_token.bezeichnung}")
    DokumentVersion.objects.create(
        dokument=dok,
        version_nr=neue_version_nr,
        dateiname=datei.name,
        inhalt_roh=dok.inhalt_roh,
        inhalt_verschluesselt=dok.inhalt_verschluesselt,
        verschluessel_nonce=dok.verschluessel_nonce,
        groesse_bytes=len(inhalt),
        kommentar=kommentar,
    )

    _protokolliere_api(request, dok, "api_upload", f"Neue Version {neue_version_nr}: {datei.name}")
    return JsonResponse({"dokument_id": dok.pk, "neue_version": neue_version_nr}, status=201)


@csrf_exempt
@api_auth_required
@require_http_methods(["GET"])
def api_kategorien(request):
    """GET /dms/api/v1/kategorien/
    Alle verfuegbaren Dokumentkategorien abrufen (fuer Upload-Vorbelegung).
    """
    kategorien = DokumentKategorie.objects.select_related("elternkategorie").all()
    return JsonResponse({
        "kategorien": [
            {
                "id": k.pk,
                "name": k.name,
                "pfad": str(k),
                "klasse": k.klasse,
                "elternkategorie_id": k.elternkategorie_id,
            }
            for k in kategorien
        ]
    })
