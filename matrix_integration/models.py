from django.conf import settings
from django.db import models


class JitsiRaum(models.Model):
    """Fest konfigurierter Jitsi-Meet-Raum mit sprechendem Namen."""

    beschreibung = models.TextField(blank=True)
    ist_aktiv = models.BooleanField(default=True)
    name = models.CharField(max_length=100, verbose_name="Anzeigename")
    org_einheit = models.ForeignKey(
        "hr.OrgEinheit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jitsi_raeume",
        verbose_name="Org-Einheit",
    )
    raum_slug = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name="Raum-Slug",
        help_text="Wird Teil der Meeting-URL, z.B. 'teammeeting-it' -> meet.georg-klein.com/teammeeting-it",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Jitsi-Raum"
        verbose_name_plural = "Jitsi-Raeume"

    def __str__(self):
        return self.name

    def get_url(self):
        """Gibt die vollstaendige Jitsi-Meeting-URL zurueck."""
        base = getattr(settings, "JITSI_BASE_URL", "").rstrip("/")
        if base:
            return f"{base}/{self.raum_slug}"
        return ""


class TeilnehmerTemplate(models.Model):
    """Vordefinierte Teilnehmergruppe fuer Matrix-Raeume."""

    TYP_CHOICES = [
        ("org_einheit", "Aus Org-Einheit (automatisch)"),
        ("manuell", "Manuell zusammengestellt"),
    ]

    beschreibung = models.TextField(blank=True)
    mitglieder = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="matrix_templates",
        verbose_name="Manuelle Mitglieder",
    )
    name = models.CharField(max_length=100)
    org_einheit = models.ForeignKey(
        "hr.OrgEinheit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="matrix_templates",
        verbose_name="Org-Einheit",
        help_text="Alle Mitglieder dieser Einheit werden automatisch eingeladen.",
    )
    typ = models.CharField(max_length=20, choices=TYP_CHOICES, default="manuell")

    class Meta:
        ordering = ["name"]
        verbose_name = "Teilnehmer-Template"
        verbose_name_plural = "Teilnehmer-Templates"

    def __str__(self):
        return self.name

    def get_user_list(self):
        """Gibt alle User des Templates zurueck (aus Org-Einheit oder manuell)."""
        if self.typ == "org_einheit" and self.org_einheit:
            from hr.models import HRMitarbeiter
            return list(
                HRMitarbeiter.objects.filter(
                    stelle__org_einheit=self.org_einheit
                ).select_related("user").values_list("user", flat=True)
            )
        return list(self.mitglieder.values_list("id", flat=True))


class MatrixRaum(models.Model):
    """Konfigurierter Matrix-Raum in PRIMA."""

    TYP_CHOICES = [
        ("bereich", "Bereichs-Chat"),
        ("abteilung", "Abteilungs-Chat"),
        ("team", "Team-Chat"),
        ("manuell", "Manueller Chat"),
        ("ping", "Ping-Kanal (Benachrichtigungen)"),
    ]

    PING_TYP_CHOICES = [
        ("allgemein", "Allgemein"),
        ("facility", "Facility / Stoermeldungen (allgemein)"),
        ("fm_elektro", "FM-Team Elektro"),
        ("fm_maler", "FM-Team Maler"),
        ("fm_sanitaer", "FM-Team Sanitaer / Heizung"),
        ("fm_schlosser", "FM-Team Schlosser"),
        ("fm_schreiner", "FM-Team Schreiner"),
        ("hr", "HR / Personal"),
        ("it", "IT / Technik"),
        ("sicherheit", "Sicherheit"),
    ]

    beschreibung = models.TextField(blank=True)
    element_url = models.URLField(
        blank=True,
        default="",
        verbose_name="Element-URL",
        help_text="z.B. https://app.element.io/#/room/!ID:georg-klein.com",
    )
    ist_aktiv = models.BooleanField(default=True)
    name = models.CharField(max_length=100)
    org_einheit = models.ForeignKey(
        "hr.OrgEinheit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="matrix_raeume",
        verbose_name="Org-Einheit",
    )
    ping_typ = models.CharField(
        max_length=20,
        choices=PING_TYP_CHOICES,
        blank=True,
        default="",
        verbose_name="Ping-Kanal-Typ",
        help_text="Nur relevant wenn Typ = Ping-Kanal.",
    )
    room_alias = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Room-Alias",
        help_text="z.B. #team-it:georg-klein.com",
    )
    room_id = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Matrix Room-ID",
        help_text="z.B. !IsrMLfIlLxJXrAIUKr:georg-klein.com",
    )
    teilnehmer_template = models.ForeignKey(
        TeilnehmerTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="matrix_raeume",
        verbose_name="Teilnehmer-Template",
    )
    typ = models.CharField(max_length=20, choices=TYP_CHOICES, default="manuell")

    class Meta:
        ordering = ["name"]
        verbose_name = "Matrix-Raum"
        verbose_name_plural = "Matrix-Raeume"

    def __str__(self):
        return self.name

    def get_element_url(self):
        """Gibt die beste verfuegbare URL zurueck."""
        if self.element_url:
            return self.element_url
        if self.room_id:
            base = getattr(settings, "MATRIX_ELEMENT_URL", "https://app.element.io")
            return f"{base}/#/room/{self.room_id}"
        return ""


class SitzungsKalender(models.Model):
    """Geplante oder wiederkehrende Sitzung mit Matrix-Benachrichtigung."""

    WOCHENTAG_CHOICES = [
        (0, "Montag"),
        (1, "Dienstag"),
        (2, "Mittwoch"),
        (3, "Donnerstag"),
        (4, "Freitag"),
        (5, "Samstag"),
        (6, "Sonntag"),
    ]

    bis = models.TimeField(verbose_name="Bis")
    beschreibung = models.TextField(blank=True)
    ende_datum = models.DateField(
        null=True,
        blank=True,
        verbose_name="Enddatum",
        help_text="Leer = laeuft unbegrenzt.",
    )
    erinnerung_minuten = models.IntegerField(
        default=15,
        verbose_name="Erinnerung (Minuten vorher)",
    )
    ist_aktiv = models.BooleanField(default=True)
    ist_wiederkehrend = models.BooleanField(default=False, verbose_name="Wiederkehrend")
    matrix_raum = models.ForeignKey(
        MatrixRaum,
        on_delete=models.PROTECT,
        related_name="sitzungen",
        verbose_name="Matrix-Raum",
    )
    name = models.CharField(max_length=200)
    erinnerung_gesendet_am = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Erinnerung gesendet am",
        help_text="Wird automatisch gesetzt nachdem die Erinnerung gesendet wurde.",
    )
    naechste_ausfuehrung = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Naechste Ausfuehrung",
    )
    start_datum = models.DateField(verbose_name="Startdatum")
    teilnehmer_template = models.ForeignKey(
        TeilnehmerTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sitzungen",
        verbose_name="Teilnehmer-Template",
    )
    von = models.TimeField(verbose_name="Von")
    wochentag = models.IntegerField(
        null=True,
        blank=True,
        choices=WOCHENTAG_CHOICES,
        verbose_name="Wochentag",
        help_text="Nur bei wiederkehrenden Sitzungen.",
    )

    class Meta:
        ordering = ["naechste_ausfuehrung", "name"]
        verbose_name = "Sitzungs-Kalender"
        verbose_name_plural = "Sitzungs-Kalender"

    def __str__(self):
        return self.name

    def berechne_naechste_ausfuehrung(self):
        """Berechnet das naechste Ausfuehrungsdatum und gibt es als datetime zurueck.

        Bei einmaligen Sitzungen: start_datum + von.
        Bei wiederkehrenden: naechster passender Wochentag ab heute + von.
        Gibt None zurueck wenn die Sitzung abgelaufen ist.
        """
        import datetime
        from django.utils import timezone

        jetzt = timezone.localtime(timezone.now())
        heute = jetzt.date()

        if self.ist_wiederkehrend and self.wochentag is not None:
            # Naechsten passenden Wochentag finden (ab heute)
            tage_bis = (self.wochentag - heute.weekday()) % 7
            kandidat = heute + datetime.timedelta(days=tage_bis)
            naechste_dt = timezone.make_aware(
                datetime.datetime.combine(kandidat, self.von)
            )
            # Falls der Termin heute war aber schon vorbei ist, eine Woche weiter
            if naechste_dt <= jetzt:
                kandidat += datetime.timedelta(weeks=1)
                naechste_dt = timezone.make_aware(
                    datetime.datetime.combine(kandidat, self.von)
                )
            # Enddatum pruefen
            if self.ende_datum and kandidat > self.ende_datum:
                return None
            return naechste_dt
        else:
            # Einmalig
            if self.start_datum < heute:
                return None
            return timezone.make_aware(
                datetime.datetime.combine(self.start_datum, self.von)
            )

    def save(self, *args, **kwargs):
        """Berechnet naechste_ausfuehrung automatisch beim Speichern."""
        if self.ist_aktiv and not self.naechste_ausfuehrung:
            self.naechste_ausfuehrung = self.berechne_naechste_ausfuehrung()
        super().save(*args, **kwargs)
