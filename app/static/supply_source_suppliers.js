/* Supplier selection is shared by upload and pull; free text never becomes an ID. */
(function () {
  "use strict";
  var form = document.getElementById("ss-start-form");
  if (!form) return;
  var search = document.getElementById("ss-supplier-search");
  var selected = document.getElementById("ss-selected-supplier");
  var results = document.getElementById("ss-supplier-results");
  var status = document.getElementById("ss-supplier-status");
  var reload = document.getElementById("ss-supplier-reload");
  var setup = document.getElementById("ss-supplier-setup");
  var currency = document.getElementById("ss-supplier-currency");
  var rate = document.getElementById("ss-supplier-rate");
  var markup = document.getElementById("ss-supplier-markup");
  var file = document.getElementById("ss-file");
  var locals = JSON.parse(document.getElementById("ss-local-suppliers").textContent);
  var options = locals.slice();
  var warning = "";
  var matches = [];
  var active = -1;
  var loading = false;

  function close() {
    results.hidden = true;
    search.setAttribute("aria-expanded", "false");
    search.removeAttribute("aria-activedescendant");
    active = -1;
  }
  function choose(option) {
    selected.value = option.id;
    search.value = option.label;
    search.setCustomValidity("");
    setup.hidden = !option.needs_setup;
    setup.disabled = !option.needs_setup;
    currency.value = "";
    rate.value = "";
    markup.value = "";
    rate.readOnly = false;
    status.textContent = option.needs_setup ? "Lieferant ausgewählt. Bitte die Vorgaben unten ausfüllen." : "Lieferant ausgewählt: " + option.label;
    close();
  }
  function render() {
    var words = search.value.toLocaleLowerCase("de-CH").trim().split(/\s+/);
    matches = options.filter(function (o) {
      return words.every(function (word) { return o.label.toLocaleLowerCase("de-CH").includes(word); });
    });
    results.replaceChildren();
    active = -1;
    matches.forEach(function (o, index) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "list-group-item list-group-item-action";
      button.id = "ss-supplier-option-" + index;
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.tabIndex = -1;
      button.textContent = o.label + (o.needs_setup ? " · neu in Tools" : "");
      button.addEventListener("click", function () { choose(o); search.focus(); });
      results.appendChild(button);
    });
    results.style.maxHeight = "18rem";
    results.style.overflowY = "auto";
    results.hidden = matches.length === 0;
    search.setAttribute("aria-expanded", String(matches.length > 0));
    search.removeAttribute("aria-activedescendant");
    status.textContent = (loading ? "Weitere Lieferanten werden aus weclapp geladen. " : "") +
      (matches.length ? matches.length + " Treffer. Lieferanten aus der Liste auswählen." : "Kein passender Lieferant gefunden.") +
      (warning ? " " + warning : "");
  }
  search.addEventListener("input", function () {
    selected.value = "";
    search.setCustomValidity("");
    setup.hidden = true;
    setup.disabled = true;
    render();
  });
  search.addEventListener("focus", render);
  search.addEventListener("keydown", function (event) {
    if (event.key === "Escape") { close(); return; }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (results.hidden) render();
      if (!matches.length) return;
      active = (active + (event.key === "ArrowDown" ? 1 : -1) + matches.length) % matches.length;
      Array.from(results.children).forEach(function (el, index) {
        el.classList.toggle("active", index === active);
        el.setAttribute("aria-selected", String(index === active));
      });
      var option = results.children[active];
      search.setAttribute("aria-activedescendant", option.id);
      option.scrollIntoView({block: "nearest"});
    } else if (event.key === "Enter" && !results.hidden) {
      event.preventDefault();
      if (active >= 0) choose(matches[active]);
      else if (matches.length === 1) choose(matches[0]);
    }
  });
  document.addEventListener("click", function (event) {
    if (!document.getElementById("ss-upload-supplier-wrap").contains(event.target)) close();
  });
  currency.addEventListener("change", function () {
    rate.readOnly = currency.value === "CHF";
    rate.value = rate.readOnly ? "1" : "";
  });
  file.addEventListener("change", function () {
    document.querySelector(".file-picker-name").textContent = file.files.length ? file.files[0].name : "Keine Datei ausgewählt";
  });
  form.addEventListener("submit", function (event) {
    if (!selected.value) {
      event.preventDefault();
      search.setCustomValidity("Bitte den Lieferanten aus der Trefferliste auswählen.");
      search.reportValidity();
      return;
    }
    var upload = !event.submitter || event.submitter.id === "ss-upload-start";
    if (upload && !file.files.length) {
      event.preventDefault();
      status.textContent = "Bitte zuerst eine Datei (xlsx oder csv) auswählen.";
    }
  });
  async function load() {
    if (loading) return;
    loading = true;
    reload.disabled = true;
    warning = "";
    status.textContent = "Lieferanten werden aus weclapp geladen…";
    try {
      var response = await fetch("/bezugsquellen/neu/lieferanten", {headers: {Accept: "application/json"}, cache: "no-store"});
      if (response.redirected) throw new Error("Bitte erneut bei Tools anmelden.");
      var data = await response.json();
      if (!response.ok) throw new Error(data.error || "weclapp-Katalog konnte nicht geladen werden.");
      options = data.suppliers;
      var current = options.find(function (o) { return o.id === selected.value; });
      if (selected.value && !current) {
        selected.value = "";
        setup.hidden = true;
        setup.disabled = true;
        warning = "Die bisherige Auswahl ist nicht mehr im aktiven weclapp-Katalog. Bitte neu auswählen.";
      }
    } catch (error) {
      options = locals.slice();
      if (selected.value && !options.some(function (o) { return o.id === selected.value; })) {
        selected.value = "";
        setup.hidden = true;
        setup.disabled = true;
      }
      warning = "Nur bereits eingerichtete Lieferanten verfügbar. " + error.message;
    } finally {
      loading = false;
      reload.disabled = false;
      if (document.activeElement === search) render();
      else status.textContent = warning || options.length + " aktive Lieferanten verfügbar. Nach Name oder Nummer suchen.";
    }
  }
  reload.addEventListener("click", load);
  load();
})();
