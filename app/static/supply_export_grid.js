/* Bezugsquellen grid: idle-flush onto POST /bezugsquellen/{id}/edits. Jspreadsheet CE v5. */
(function () {
  var STATUS_SAVED = "Gespeichert";
  var STATUS_SAVING = "Wird gespeichert…";
  var STATUS_ERROR = "Nicht gespeichert — Verbindung prüfen";
  var applying = false;
  var queue = [];
  var timer = null;
  var flushing = false;
  var worksheet = null;
  var config = null;
  var statusEl = null;

  function $(id) {
    return document.getElementById(id);
  }

  function setStatus(text, kind) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.classList.remove("is-saving", "is-error", "is-saved");
    statusEl.classList.add(kind);
  }

  function fieldAt(x) {
    if (!config || !config.fields) return null;
    return config.fields[x] || null;
  }

  function isQueuedField(field) {
    if (!field || !config) return false;
    var allowed = config.editableFields;
    if (allowed && allowed.length) return allowed.indexOf(field) >= 0;
    return field !== "_status" && field !== "ek_after" && field !== "sale_chf";
  }

  function encodeValue(field, value) {
    if (value == null) return "";
    return String(value);
  }

  function queueChange(x, y, value) {
    if (applying || !config || !config.editable) return;
    var field = fieldAt(x);
    if (!isQueuedField(field)) return;
    var rowId = config.rowIds[y];
    if (!rowId) return;
    queue.push({ row_id: rowId, field: field, value: encodeValue(field, value) });
    var col = config.columns && config.columns[x];
    if (col && col.maxLength && String(value || "").length > col.maxLength) {
      setStatus("Warnung: " + (col.title || field) + " länger als " + col.maxLength + " Zeichen", "is-error");
    } else {
      setStatus(STATUS_SAVING, "is-saving");
    }
    scheduleFlush();
  }

  function scheduleFlush() {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      timer = null;
      flush(false);
    }, config.idleMs || 400);
  }

  function onEvent(event) {
    if (event !== "onchange") return;
    var x = arguments[3];
    var y = arguments[4];
    var value = arguments[5];
    queueChange(Number(x), Number(y), value);
  }

  function colIndex(field) {
    return config.fields.indexOf(field);
  }

  function applyRowState(y, state) {
    if (!worksheet || !worksheet.rows || !worksheet.rows[y]) return;
    var tr = worksheet.rows[y].element;
    if (!tr || !state) return;
    tr.classList.toggle("row-highlighted", !!state.highlighted);
    tr.classList.toggle("row-unresolved", !!state.unresolved);
  }

  function applyServerRows(rows) {
    if (!worksheet || !rows) return;
    applying = true;
    try {
      for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        var y = config.rowIds.indexOf(row.id);
        if (y < 0) continue;
        var values = row.values || {};
        Object.keys(values).forEach(function (field) {
          var x = colIndex(field);
          if (x >= 0) worksheet.setValueFromCoords(x, y, values[field], true);
        });
        if (config.rowState[y]) {
          config.rowState[y].changed = row.changed;
          config.rowState[y].highlighted = row.highlighted;
          config.rowState[y].unresolved = row.unresolved;
          config.rowState[y].override = row.override;
        }
        applyRowState(y, config.rowState[y]);
      }
    } finally {
      applying = false;
    }
  }

  function paintInitial() {
    if (!config || !config.rowState) return;
    for (var y = 0; y < config.rowState.length; y++) {
      applyRowState(y, config.rowState[y]);
    }
  }

  function flush(keepalive) {
    if (timer) {
      window.clearTimeout(timer);
      timer = null;
    }
    if (!queue.length || flushing || !config) return;
    var payload = queue.slice();
    queue = [];
    flushing = true;
    setStatus(STATUS_SAVING, "is-saving");

    var body = JSON.stringify(payload);
    var url = config.editsUrl;

    function fail() {
      queue = payload.concat(queue);
      flushing = false;
      setStatus(STATUS_ERROR, "is-error");
      window.setTimeout(function () {
        flush(false);
      }, 1500);
    }

    function succeed(data) {
      flushing = false;
      applyServerRows(data && data.rows);
      if (queue.length) {
        setStatus(STATUS_SAVING, "is-saving");
        scheduleFlush();
      } else {
        setStatus(STATUS_SAVED, "is-saved");
      }
    }

    if (keepalive && navigator.sendBeacon) {
      var blob = new Blob([body], { type: "application/json" });
      if (!navigator.sendBeacon(url, blob)) fail();
      else succeed({ rows: [] });
      return;
    }

    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: body,
      keepalive: !!keepalive,
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, status: response.status, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          var message = (result.data && result.data.error) || STATUS_ERROR;
          queue = payload.concat(queue);
          flushing = false;
          setStatus(message, "is-error");
          if (result.status >= 500) {
            window.setTimeout(function () {
              flush(false);
            }, 1500);
          }
          return;
        }
        succeed(result.data);
      })
      .catch(fail);
  }

  function destroyExisting(el) {
    if (!el || typeof jspreadsheet === "undefined") return;
    try {
      if (typeof jspreadsheet.destroy === "function") {
        jspreadsheet.destroy(el, true);
      }
    } catch (err) {
      /* already gone */
    }
    el.innerHTML = "";
  }

  /**
   * Nest/# index is hidden via hideIndex + matching CSS (td AND col). Freeze
   * data columns from left: 0 with configured widths — never measured
   * offsetWidth (0 mid-layout) and never collapse the nest col to width 0
   * while its cells are display:none (that maps Artikelnr. onto a 0-col).
   */
  function hardenFreeze(ws) {
    var n = Number(ws && ws.options && ws.options.freezeColumns) || 0;
    if (!n || !ws.headers) return;

    var table =
      ws.table ||
      (ws.element && ws.element.querySelector ? ws.element.querySelector("table") : null);
    if (!table) return;

    if (typeof ws.hideIndex === "function") {
      ws.hideIndex();
    } else {
      table.classList.add("jss_hidden_index");
    }

    var left = 0;
    for (var s = 0; s < n; s++) {
      var configured = 100;
      if (ws.options.columns && ws.options.columns[s] && ws.options.columns[s].width) {
        configured = parseInt(ws.options.columns[s].width, 10) || 100;
      }
      if (ws.cols && ws.cols[s] && ws.cols[s].colElement) {
        ws.cols[s].colElement.setAttribute("width", String(configured));
        ws.cols[s].colElement.style.setProperty("width", configured + "px", "important");
        ws.cols[s].colElement.style.setProperty("min-width", configured + "px", "important");
      }

      var header = ws.headers[s];
      if (header) {
        header.classList.add("jss_freezed");
        header.style.setProperty("position", "sticky", "important");
        header.style.setProperty("left", left + "px", "important");
        header.style.setProperty("min-width", configured + "px", "important");
        header.style.setProperty("max-width", configured + "px", "important");
      }
      if (ws.records) {
        for (var r = 0; r < ws.records.length; r++) {
          var cell = ws.records[r] && ws.records[r][s];
          if (cell && cell.element) {
            cell.element.classList.add("jss_freezed");
            cell.element.style.setProperty("position", "sticky", "important");
            cell.element.style.setProperty("left", left + "px", "important");
            cell.element.style.setProperty("min-width", configured + "px", "important");
            cell.element.style.setProperty("max-width", configured + "px", "important");
          }
        }
      }
      left += configured;
    }
    ws.options.freezeColumns = 0;
  }

  function bindColumnPicker(scope) {
    var picker = scope.querySelector ? scope.querySelector("#supply-column-picker") : $("supply-column-picker");
    var toggle = scope.querySelector ? scope.querySelector("#supply-column-toggle") : $("supply-column-toggle");
    if (!picker || !toggle) return;

    toggle.addEventListener("click", function () {
      var hidden = picker.hasAttribute("hidden");
      if (hidden) picker.removeAttribute("hidden");
      else picker.setAttribute("hidden", "");
      toggle.setAttribute("aria-expanded", hidden ? "true" : "false");
    });

    function collectVisible() {
      var keys = [];
      var inputs = picker.querySelectorAll('input[type="checkbox"]');
      for (var i = 0; i < inputs.length; i++) {
        if (inputs[i].checked) keys.push(inputs[i].value);
      }
      return keys;
    }

    function persist(body) {
      flush(false);
      fetch("/bezugsquellen/spalten", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(body),
      })
        .then(function (response) {
          if (!response.ok) throw new Error("Spalten konnten nicht gespeichert werden");
          window.location.reload();
        })
        .catch(function (err) {
          setStatus(String((err && err.message) || err), "is-error");
        });
    }

    picker.addEventListener("change", function (event) {
      var target = event.target;
      if (!target || target.type !== "checkbox") return;
      persist({ visible: collectVisible() });
    });

    var presetButtons = picker.querySelectorAll("[data-column-preset]");
    for (var p = 0; p < presetButtons.length; p++) {
      presetButtons[p].addEventListener("click", function (event) {
        var id = event.currentTarget.getAttribute("data-column-preset");
        persist({ preset: id });
      });
    }
  }

  function showInitError(el, err) {
    if (!el) return;
    el.innerHTML =
      '<p class="error-banner">Tabelle konnte nicht geladen werden: ' +
      String((err && err.message) || err) +
      "</p>";
  }

  function init(root) {
    try {
      var scope = root && root.querySelector ? root : document;
      var el = scope.querySelector ? scope.querySelector("#supply-spreadsheet") : $("supply-spreadsheet");
      var cfgEl = scope.querySelector ? scope.querySelector("#supply-grid-config") : $("supply-grid-config");
      statusEl = scope.querySelector ? scope.querySelector("#supply-save-status") : $("supply-save-status");
      if (!el || !cfgEl) return;
      if (typeof jspreadsheet !== "function") {
        showInitError(el, "jspreadsheet ist nicht geladen");
        return;
      }
      config = JSON.parse(cfgEl.textContent);
      queue = [];
      flushing = false;
      destroyExisting(el);

      var worksheets = jspreadsheet(el, {
        parseFormulas: false,
        autoCasting: false,
        autoIncrement: false,
        toolbar: false,
        about: false,
        onevent: onEvent,
        worksheets: [
          {
            data: config.data,
            columns: config.columns,
            freezeColumns: config.freezeColumns || 0,
            filters: false,
            search: false,
            tableOverflow: true,
            tableWidth: "100%",
            tableHeight: "70vh",
            editable: !!config.editable,
            allowComments: false,
            allowInsertRow: false,
            allowDeleteRow: false,
            allowInsertColumn: false,
            allowDeleteColumn: false,
            allowManualInsertRow: false,
            allowManualInsertColumn: false,
            allowRenameColumn: false,
            columnDrag: false,
            rowDrag: false,
            selectionCopy: true,
            contextMenu: false,
            parseFormulas: false,
          },
        ],
      });
      worksheet = worksheets && worksheets[0] ? worksheets[0] : worksheets;
      hardenFreeze(worksheet);
      paintInitial();
      bindColumnPicker(scope);
      if (statusEl && !statusEl.textContent) setStatus(STATUS_SAVED, "is-saved");
    } catch (err) {
      var fallback = (root && root.querySelector && root.querySelector("#supply-spreadsheet")) || $(
        "supply-spreadsheet"
      );
      showInitError(fallback, err);
      console.error("supply_export_grid init failed", err);
    }
  }

  function onBlur() {
    flush(false);
  }

  function onUnload() {
    flush(true);
  }

  function reinitLivePanel() {
    var panel = document.getElementById("supply-export-grid-panel");
    if (panel) init(panel);
  }

  document.addEventListener("DOMContentLoaded", function () {
    init(document);
  });
  // outerHTML replaces the target, so event.detail.target is detached — always
  // re-init from the live panel in the document (same as snapshot_grid.js).
  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail && event.detail.target;
    var elt = event.detail && event.detail.elt;
    if (
      !(
        (target && target.id === "supply-export-grid-panel") ||
        (elt && elt.id === "supply-export-grid-panel")
      )
    ) {
      return;
    }
    reinitLivePanel();
  });
  window.addEventListener("blur", onBlur);
  window.addEventListener("beforeunload", onUnload);

  if (document.readyState !== "loading") {
    init(document);
  }
})();
