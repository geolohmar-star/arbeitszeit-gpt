"""
Management Command: Erstellt die interne Root-CA und Mitarbeiter-Zertifikate.

Aufruf:
  python manage.py erstelle_ca              # Root-CA + alle Mitarbeiter
  python manage.py erstelle_ca --nur_ca     # Nur Root-CA
  python manage.py erstelle_ca --user max   # Einzelnen User
"""
import datetime
import uuid

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Erstellt interne Root-CA und Mitarbeiter-Zertifikate"

    def add_arguments(self, parser):
        parser.add_argument("--nur_ca", action="store_true",
                            help="Nur Root-CA erstellen")
        parser.add_argument("--user", type=str, default=None,
                            help="Nur fuer diesen Username")
        parser.add_argument("--gueltig_jahre", type=int, default=2,
                            help="Gueltigkeitsdauer in Jahren (Standard: 2)")

    def handle(self, *args, **options):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from signatur.models import MitarbeiterZertifikat, RootCA

        # ------------------------------------------------------------------
        # 1. Root-CA anlegen (falls noch nicht vorhanden)
        # ------------------------------------------------------------------
        if RootCA.objects.exists():
            self.stdout.write("Root-CA bereits vorhanden – wird weiterverwendet.")
            root_ca = RootCA.objects.first()
            root_cert_pem = root_ca.zertifikat_pem.encode()
        else:
            self.stdout.write("Erstelle Root-CA...")
            root_key, root_cert, root_cert_pem = self._erstelle_root_ca()

            root_key_pem = root_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )

            gueltig_bis = datetime.date.today() + datetime.timedelta(days=10 * 365)
            root_ca = RootCA.objects.create(
                zertifikat_pem=root_cert_pem.decode(),
                gueltig_bis=gueltig_bis,
                organisation="Intern",
                common_name="Interne Root CA",
            )
            # Root-Key separat speichern (nur fuer CA-Betrieb noetig)
            import os
            ca_key_pfad = os.path.join("signatur", "ca_root.key.pem")
            with open(ca_key_pfad, "wb") as f:
                f.write(root_key_pem)
            self.stdout.write(self.style.WARNING(
                f"Root-CA-Schluessel gespeichert: {ca_key_pfad} "
                "(SICHER AUFBEWAHREN – nicht committen!)"
            ))
            self.stdout.write(self.style.SUCCESS("Root-CA erstellt."))

        if options["nur_ca"]:
            return

        # ------------------------------------------------------------------
        # 2. Mitarbeiter-Zertifikate ausstellen
        # ------------------------------------------------------------------
        from django.contrib.auth import get_user_model
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography import x509
        from cryptography.x509.oid import NameOID

        User = get_user_model()

        if options["user"]:
            users = User.objects.filter(username=options["user"])
        else:
            users = User.objects.filter(is_active=True)

        # Root-Key laden
        import os
        ca_key_pfad = os.path.join("signatur", "ca_root.key.pem")
        if not os.path.exists(ca_key_pfad):
            self.stdout.write(self.style.ERROR(
                f"Root-CA-Schluessel nicht gefunden: {ca_key_pfad}. "
                "Erst 'python manage.py erstelle_ca --nur_ca' ausfuehren."
            ))
            return

        with open(ca_key_pfad, "rb") as f:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            root_key = load_pem_private_key(f.read(), password=None)

        from cryptography.x509 import load_pem_x509_certificate
        root_cert = load_pem_x509_certificate(root_cert_pem)

        gueltig_jahre = options["gueltig_jahre"]
        erstellt = 0
        uebersprungen = 0

        for user in users:
            if MitarbeiterZertifikat.objects.filter(user=user, status="aktiv").exists():
                uebersprungen += 1
                continue

            name = user.get_full_name() or user.username
            email = user.email or f"{user.username}@intern.local"

            # User-Schluessel erzeugen
            user_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048
            )

            # Zertifikat ausstellen
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
            erstellt += 1
            self.stdout.write(f"  Zertifikat fuer {name} ({email}) ausgestellt.")

        self.stdout.write(self.style.SUCCESS(
            f"Fertig: {erstellt} Zertifikate ausgestellt, {uebersprungen} bereits vorhanden."
        ))

    # ------------------------------------------------------------------
    def _erstelle_root_ca(self):
        import datetime
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        jetzt = datetime.datetime.now(datetime.timezone.utc)

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "DE"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Intern"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Interne Root CA"),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(jetzt)
            .not_valid_after(jetzt + datetime.timedelta(days=10 * 365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        return key, cert, cert_pem
