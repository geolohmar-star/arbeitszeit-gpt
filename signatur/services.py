"""
Zentraler Einstiegspunkt fuer alle Signatur-Operationen.

Einzige Import-Stelle fuer Views und andere Apps:

    from signatur.services import get_backend, signiere_pdf

Der konkrete Backend wird per settings.SIGNATUR_BACKEND bestimmt:
  "intern"   → pyhanko + interne CA (Standard, offline)
  "sign_me"  → Bundesdruckerei sign-me (QES, benoetigt Gateway)
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_BACKEND_CACHE = None


def get_backend():
    """
    Gibt den konfigurierten Signatur-Backend zurueck.
    Wird gecacht nach erstem Aufruf.
    """
    global _BACKEND_CACHE
    if _BACKEND_CACHE is not None:
        return _BACKEND_CACHE

    backend_name = getattr(settings, "SIGNATUR_BACKEND", "intern")

    if backend_name == "intern":
        from signatur.backends.intern import InternBackend
        _BACKEND_CACHE = InternBackend()
    elif backend_name == "sign_me":
        from signatur.backends.sign_me import SignMeBackend
        _BACKEND_CACHE = SignMeBackend()
    else:
        raise ValueError(
            f"Unbekannter SIGNATUR_BACKEND: '{backend_name}'. "
            "Erlaubt: 'intern', 'sign_me'"
        )

    logger.info("Signatur-Backend: %s (%s)", backend_name, _BACKEND_CACHE.SIGNATUR_TYP)
    return _BACKEND_CACHE


def erstelle_mitarbeiter_zertifikat(user, gueltig_jahre: int = 2) -> bool:
    """
    Erstellt automatisch ein Signatur-Zertifikat fuer einen Django-User.

    Wird als Signal-Handler bei Anlage neuer HRMitarbeiter aufgerufen.
    Gibt True zurueck wenn ein Zertifikat angelegt wurde, False wenn bereits
    eines vorhanden oder die Root-CA nicht verfuegbar ist.

    Verwendung:
        from signatur.services import erstelle_mitarbeiter_zertifikat
        erstelle_mitarbeiter_zertifikat(user)
    """
    import base64
    import datetime
    import os
    import uuid

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from cryptography.x509.oid import NameOID
    from signatur.models import MitarbeiterZertifikat, RootCA

    # Bereits vorhanden?
    if MitarbeiterZertifikat.objects.filter(user=user, status="aktiv").exists():
        logger.debug("Zertifikat fuer %s bereits vorhanden – uebersprungen.", user.username)
        return False

    # Root-CA aus DB laden
    root_ca = RootCA.objects.first()
    if not root_ca:
        logger.warning("Kein Root-CA vorhanden – Zertifikat fuer %s nicht ausgestellt.", user.username)
        return False

    # Root-Key laden: erst Datei, dann Umgebungsvariable
    ca_key_pfad = os.path.join("signatur", "ca_root.key.pem")
    ca_key_b64 = os.environ.get("CA_ROOT_KEY_B64", "")

    if os.path.exists(ca_key_pfad):
        with open(ca_key_pfad, "rb") as f:
            root_key_pem_bytes = f.read()
    elif ca_key_b64:
        root_key_pem_bytes = base64.b64decode(ca_key_b64)
    else:
        logger.warning(
            "Root-CA-Schluessel nicht gefunden – Zertifikat fuer %s nicht ausgestellt.",
            user.username,
        )
        return False

    root_key = load_pem_private_key(root_key_pem_bytes, password=None)
    from cryptography.x509 import load_pem_x509_certificate
    root_cert = load_pem_x509_certificate(root_ca.zertifikat_pem.encode())

    name = user.get_full_name() or user.username
    email = user.email or f"{user.username}@intern.local"

    # User-Schluessel erzeugen
    user_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    seriennummer = int(uuid.uuid4().hex[:12], 16)
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    gueltig_bis_dt = jetzt + datetime.timedelta(days=gueltig_jahre * 365)

    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, name),
            x509.NameAttribute(NameOID.EMAIL_ADDRESS, email),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Intern"),
        ]))
        .issuer_name(root_cert.subject)
        .public_key(user_key.public_key())
        .serial_number(seriennummer)
        .not_valid_before(jetzt)
        .not_valid_after(gueltig_bis_dt)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=True,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.RFC822Name(email)]),
            critical=False,
        )
    )
    zert = builder.sign(root_key, hashes.SHA256())

    cert_pem = zert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = user_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    fingerprint = zert.fingerprint(hashes.SHA256()).hex()

    # Privaten Schluessel sofort verschluesseln wenn Session-Schluessel verfuegbar
    from signatur.crypto import (
        get_session_schluessel,
        leite_schluessel_ab,
        verschluessele_privaten_schluessel,
    )
    dk_hex = get_session_schluessel()
    if dk_hex:
        # Session-Schluessel vorhanden → verschluesselt speichern
        # Wir brauchen das Passwort um zu verschluesseln, aber wir haben nur den abgeleiteten
        # Schluessel – daher einmalig mit zufaelligem Salt neu ableiten
        # BESSER: Schluessel direkt als "Passwort" fuer eine zweite Ableitungsrunde nutzen
        import os as _os
        salt = _os.urandom(32)
        nonce = _os.urandom(12)
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        # Den vorhandenen 32-Byte-Schluessel als Verschluesselungsschluessel direkt nutzen
        aes_schluessel = bytes.fromhex(dk_hex)
        aesgcm = AESGCM(aes_schluessel)
        verschluesselt = aesgcm.encrypt(nonce, key_pem.encode("utf-8"), None)
        MitarbeiterZertifikat.objects.create(
            user=user,
            zertifikat_pem=cert_pem,
            privater_schluessel_pem="",
            privater_schluessel_verschluesselt=verschluesselt,
            schluessel_salt=salt.hex(),
            schluessel_nonce=nonce.hex(),
            seriennummer=str(seriennummer),
            gueltig_von=datetime.date.today(),
            gueltig_bis=gueltig_bis_dt.date(),
            fingerprint_sha256=fingerprint,
            status="aktiv",
        )
        logger.info(
            "Signatur-Zertifikat mit verschluesseltem Schluessel ausgestellt fuer %s.",
            user.username,
        )
    else:
        # Kein Session-Schluessel (z.B. Management-Command) → Plaintext,
        # wird beim naechsten Login automatisch verschluesselt
        MitarbeiterZertifikat.objects.create(
            user=user,
            zertifikat_pem=cert_pem,
            privater_schluessel_pem=key_pem,
            seriennummer=str(seriennummer),
            gueltig_von=datetime.date.today(),
            gueltig_bis=gueltig_bis_dt.date(),
            fingerprint_sha256=fingerprint,
            status="aktiv",
        )
        logger.info(
            "Signatur-Zertifikat (Plaintext, wird beim Login migriert) ausgestellt fuer %s.",
            user.username,
        )
    return True


def signiere_pdf(pdf_bytes: bytes, user, dokument_name: str = "Dokument",
                 sichtbar: bool = True, **kwargs) -> bytes:
    """
    Komfort-Funktion: PDF signieren in einer Zeile.

    Verwendung in Views:
        from signatur.services import signiere_pdf
        signiertes = signiere_pdf(pdf_bytes, request.user, "Zeitgutschrift")

    Args:
        pdf_bytes:      Unsigniertes PDF
        user:           Django-User (Unterzeichner)
        dokument_name:  Name des Dokuments (fuer Protokoll)
        sichtbar:       Sichtbaren Stempel einbetten (Standard: True)
        **kwargs:       Weitere Metadaten (content_type, object_id, seite)

    Returns:
        Signiertes PDF als bytes
    """
    backend = get_backend()
    meta = {
        "dokument_name": dokument_name,
        "sichtbar": sichtbar,
        **kwargs,
    }
    return backend.signiere_direkt(pdf_bytes, user, meta)
