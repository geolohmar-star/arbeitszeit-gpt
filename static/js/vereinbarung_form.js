document.addEventListener('DOMContentLoaded', function() {

  // --- 2. Arbeitszeit-Typ Toggle (muss vor handleAntragsartChange definiert sein) ---
  var regelRadio = document.getElementById('radio-regelmaessig');
  var indivRadio = document.getElementById('radio-individuell');
  var regelSection = document.getElementById('regelmaessig-section');
  var indivSection = document.getElementById('individuell-section');

  function toggleArbeitszeit() {
    if (regelRadio && regelRadio.checked) {
      if (regelSection) { regelSection.style.display = 'block'; regelSection.style.visibility = 'visible'; }
      if (indivSection) { indivSection.style.display = 'none'; indivSection.style.visibility = 'hidden'; }
    } else if (indivRadio && indivRadio.checked) {
      if (indivSection) { indivSection.style.display = 'block'; indivSection.style.visibility = 'visible'; }
      if (regelSection) { regelSection.style.display = 'none'; regelSection.style.visibility = 'hidden'; }
    } else {
      // Kein Radio gewaehlt: beide ausblenden
      if (regelSection) regelSection.style.display = 'none';
      if (indivSection) indivSection.style.display = 'none';
    }
  }

  if (regelRadio) regelRadio.addEventListener('change', toggleArbeitszeit);
  if (indivRadio) indivRadio.addEventListener('change', toggleArbeitszeit);

  // --- 1. Antragsart Toggle ---
  var antragsartRadios = document.querySelectorAll('input[name="antragsart"]');
  var arbeitszeitCard = document.getElementById('arbeitszeit-card');
  var weiterbewilligungCard = document.getElementById('weiterbewilligung-card');
  var gueltigkeitTitle = document.getElementById('gueltigkeits-title');
  var datumLabel = document.getElementById('datum-label');
  var datumHelp = document.getElementById('datum-help');
  var datumInput = document.getElementById('datum_input');
  var gueltigAbGroup = document.getElementById('gueltig-ab-group');
  var gueltigBisGroup = document.getElementById('gueltig-bis-group');
  var telearbeitCard = document.getElementById('telearbeit-card');

  function handleAntragsartChange(value) {
    if (value === 'beendigung') {
      if (arbeitszeitCard) arbeitszeitCard.style.display = 'none';
      if (weiterbewilligungCard) weiterbewilligungCard.style.display = 'none';
      if (telearbeitCard) telearbeitCard.style.display = 'none';
      if (gueltigkeitTitle) gueltigkeitTitle.textContent = '2. Beendigungsdatum';
      if (datumLabel) datumLabel.innerHTML = 'Beendigung zum <span class="required">*</span>';
      if (datumHelp) datumHelp.textContent = 'Datum, zu dem die Vereinbarung beendet werden soll';
      if (gueltigAbGroup) gueltigAbGroup.style.display = 'block';
      if (gueltigBisGroup) gueltigBisGroup.style.display = 'none';
      if (datumInput) { datumInput.name = 'gueltig_ab'; datumInput.required = true; }
    } else if (value === 'weiterbewilligung') {
      if (arbeitszeitCard) arbeitszeitCard.style.display = 'none';
      if (weiterbewilligungCard) weiterbewilligungCard.style.display = 'block';
      if (telearbeitCard) telearbeitCard.style.display = 'none';
      if (gueltigkeitTitle) gueltigkeitTitle.textContent = '3. Gueltigkeit';
      if (datumLabel) datumLabel.innerHTML = 'Gueltig ab <span class="required">*</span>';
      if (datumHelp) datumHelp.textContent = 'Datum, ab dem die Vereinbarung gueltig ist';
      if (gueltigAbGroup) gueltigAbGroup.style.display = 'none';
      if (gueltigBisGroup) gueltigBisGroup.style.display = 'block';
      if (datumInput) { datumInput.name = 'gueltig_ab'; datumInput.required = false; }
    } else {
      // Ersteinrichtung, Verringerung, Erhoehung
      if (arbeitszeitCard) arbeitszeitCard.style.display = 'block';
      if (weiterbewilligungCard) weiterbewilligungCard.style.display = 'none';
      if (telearbeitCard) telearbeitCard.style.display = 'block';
      if (gueltigkeitTitle) gueltigkeitTitle.textContent = '3. Gueltigkeit';
      if (datumLabel) datumLabel.innerHTML = 'Gueltig ab <span class="required">*</span>';
      if (datumHelp) datumHelp.textContent = 'Datum, ab dem die Vereinbarung gueltig ist';
      if (gueltigAbGroup) gueltigAbGroup.style.display = 'block';
      if (gueltigBisGroup) gueltigBisGroup.style.display = 'block';
      if (datumInput) { datumInput.name = 'gueltig_ab'; datumInput.required = true; }
      toggleArbeitszeit();
    }
  }

  if (antragsartRadios.length > 0) {
    antragsartRadios.forEach(function(radio) {
      radio.addEventListener('change', function() {
        handleAntragsartChange(this.value);
      });
    });
    var checkedRadio = document.querySelector('input[name="antragsart"]:checked');
    if (checkedRadio) {
      handleAntragsartChange(checkedRadio.value);
    }
  }

  // Initialer Zustand
  toggleArbeitszeit();

  // --- 3. Wochen hinzufuegen Logik ---
  var addWeekBtn = document.getElementById('add-week');
  var weeksContainer = document.getElementById('weeks-container');
  var weekCount = document.querySelectorAll('.week').length;
  var zyklusContainer = document.getElementById('zyklus-startdatum-container');
  var zyklusInput = document.getElementById('zyklus_startdatum');

  var firstRemoveBtn = document.querySelector('.week .remove-week');
  if (firstRemoveBtn) {
    firstRemoveBtn.style.display = 'none';
  }

  function aktualisiereMehrwochenHinweis() {
    if (!zyklusContainer || !zyklusInput) return;
    var aktuelleWochen = weeksContainer ? weeksContainer.querySelectorAll('.week').length : 1;
    if (aktuelleWochen > 1) {
      zyklusContainer.style.display = 'block';
      zyklusInput.required = true;
    } else {
      zyklusContainer.style.display = 'none';
      zyklusInput.required = false;
      zyklusInput.value = '';
    }
  }

  if (addWeekBtn && weeksContainer) {
    addWeekBtn.addEventListener('click', function() {
      weekCount++;
      var originalWeek = weeksContainer.querySelector('.week');
      var newWeek = originalWeek.cloneNode(true);
      newWeek.dataset.week = weekCount;

      var titleElement = newWeek.querySelector('.week-title');
      if (titleElement) {
        titleElement.textContent = 'Woche ' + weekCount;
      }

      newWeek.querySelectorAll('input').forEach(function(input) {
        input.value = '';
        var parts = input.name.split('_');
        if (parts.length >= 3) {
          input.name = parts[0] + '_' + parts[1] + '_' + weekCount;
        }
      });

      var removeBtn = newWeek.querySelector('.remove-week');
      if (removeBtn) {
        removeBtn.style.display = 'inline-block';
        removeBtn.onclick = function() {
          newWeek.remove();
          aktualisiereMehrwochenHinweis();
        };
      }

      weeksContainer.appendChild(newWeek);
      aktualisiereMehrwochenHinweis();
    });
  }

  // Validierung: Startdatum muss ein Montag sein
  if (zyklusInput) {
    zyklusInput.addEventListener('change', function() {
      if (!this.value) return;
      var datum = new Date(this.value);
      if (datum.getDay() !== 1) {
        this.setCustomValidity('Das Startdatum muss ein Montag sein.');
        this.reportValidity();
      } else {
        this.setCustomValidity('');
      }
    });
  }
});
