/* Supply-source resolve grid: idle-flush queue + bulk rates. Jspreadsheet CE v5. */
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
    var allowed = config.editableFields || [];
    return allowed.indexOf(field) >= 0;
  }

  function queueChange(x, y, value) {
    if (applying || !config || !config.editable) return;
    var field = fieldAt(x);
    if (!isQueuedField(field)) return;
    var rowId = config.rowIds[y];
    if (!rowId) return;
    queue.push({ row_id: rowId, field: field, value: value == null ? "" : String(value) });
    setStatus(STATUS_SAVING, "is-saving");
    scheduleFlush();
  }

  function scheduleFlush() {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      timer = null;
      flush(false);
    }, config.idleMs || 400);
  }

  function onBeforeChange(el, cell, x, y) {
    if (!config) return true;
    var field = fieldAt(Number(x));
    if (field === "unit_id") {
      var locked = (config.unitLockedRows || []).indexOf(Number(y)) >= 0;
      if (locked) return false;
    }
    return true;
  }

  function onEvent(event) {
    if (event !== "onchange") return;
    queueChange(Number(arguments[3]), Number(arguments[4]), arguments[5]);
  }

  function rowIsHidden(y) {
    var row = worksheet.rows && worksheet.rows[y];
    return !!(row && row.element && row.element.style.display === "none");
  }

  function visibleRowIds() {
    var ids = [];
    if (!worksheet || !config) return ids;
    var last = config.rowIds.length;
    for (var y = 0; y < last; y++) {
      if (rowIsHidden(y)) continue;
      ids.push(config.rowIds[y]);
    }
    return ids;
  }

  function applyFilters() {
    if (!worksheet || !config) return;
    var code = ($("ss-filter-code") && $("ss-filter-code").value) || "";
    var prefix = (($("ss-filter-prefix") && $("ss-filter-prefix").value) || "").toLowerCase();
    var name = (($("ss-filter-name") && $("ss-filter-name").value) || "").toLowerCase();
    var match = ($("ss-filter-match") && $("ss-filter-match").value) || "";
    var intent = ($("ss-filter-intent") && $("ss-filter-intent").value) || "";
    var last = config.data.length;
    for (var y = 0; y < last; y++) {
      var row = config.data[y];
      var show = true;
      if (code && String(row[4] || "") !== code) show = false;
      if (prefix && String(row[0] || "").toLowerCase().indexOf(prefix) !== 0) show = false;
      if (name && String(row[1] || "").toLowerCase().indexOf(name) < 0) show = false;
      if (match === "matched" && String(row[14] || "").indexOf("ohne Zuordnung") >= 0) show = false;
      if (match === "unmatched" && String(row[14] || "").indexOf("ohne Zuordnung") < 0) show = false;
      if (intent && String(row[15] || "") !== intent) show = false;
      var el = worksheet.rows && worksheet.rows[y] && worksheet.rows[y].element;
      if (el) el.style.display = show ? "" : "none";
    }
  }

  function selectVisible() {
    if (!worksheet || !config) return;
    var first = -1;
    var last = -1;
    for (var y = 0; y < config.rowIds.length; y++) {
      if (rowIsHidden(y)) continue;
      if (first < 0) first = y;
      last = y;
    }
    if (first < 0) return;
    worksheet.updateSelectionFromCoords(0, first, 0, last);
  }

  function markUnmatched() {
    if (!worksheet || !config) return;
    (config.unmatchedRows || []).forEach(function (y) {
      var el = worksheet.rows && worksheet.rows[y] && worksheet.rows[y].element;
      if (el) el.classList.add("ss-row-unmatched");
    });
  }

  function markUnitLocked() {
    if (!worksheet || !config) return;
    var x = (config.fields || []).indexOf("unit_id");
    if (x < 0) return;
    var hint = config.unitLockedHint || "";
    var descById = {};
    (config.units || []).forEach(function (u) {
      descById[u.id] = u.description || "";
    });
    for (var y = 0; y < (config.rowIds || []).length; y++) {
      var cell = null;
      try {
        cell = worksheet.getCell(x, y);
      } catch (err) {
        cell = null;
      }
      if (!cell) continue;
      var uid = String((config.data[y] && config.data[y][x]) || "");
      var parts = [];
      if (descById[uid]) parts.push(descById[uid]);
      if ((config.unitLockedRows || []).indexOf(y) >= 0) {
        cell.classList.add("ss-unit-locked");
        parts.push(hint);
      }
      if (parts.length) cell.title = parts.join(" — ");
    }
  }

  function replaceGrid(next) {
    config = next;
    var el = $("ss-spreadsheet");
    if (el && typeof jspreadsheet.destroy === "function") {
      try { jspreadsheet.destroy(el, true); } catch (err) {}
    }
    applying = true;
    try {
      var sheets = jspreadsheet(el, {
        worksheets: [{
          data: config.data,
          columns: config.columns,
          tableOverflow: true,
          tableWidth: "100%",
          tableHeight: "70vh",
          freezeColumns: 1,
          allowInsertRow: false,
          allowDeleteRow: false,
          allowInsertColumn: false,
          allowDeleteColumn: false,
          columnSorting: false,
          onbeforechange: onBeforeChange,
          onchange: onEvent,
        }],
      });
      worksheet = sheets[0];
    } finally {
      applying = false;
    }
    markUnmatched();
    markUnitLocked();
    applyFilters();
    var unset = $("ss-discount-unset");
    if (unset && typeof config.discountUnset === "number") {
      unset.textContent = String(config.discountUnset);
    }
    var approve = $("ss-approve");
    if (approve && config.editable) {
      var blocked = (config.discountUnset || 0) > 0
        || (config.unmatchedRows || []).length > 0
        || (config.createNoUnit || 0) > 0;
      approve.disabled = blocked;
    }
  }

  function flush() {
    if (flushing || !queue.length || !config) return;
    flushing = true;
    var batch = queue.slice();
    queue = [];
    fetch(config.editsUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(batch),
    })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        flushing = false;
        if (!res.ok) {
          queue = batch.concat(queue);
          setStatus((res.body && res.body.error) || STATUS_ERROR, "is-error");
          return;
        }
        if (res.body.grid) replaceGrid(res.body.grid);
        setStatus(STATUS_SAVED, "is-saved");
        if (queue.length) scheduleFlush();
      })
      .catch(function () {
        flushing = false;
        queue = batch.concat(queue);
        setStatus(STATUS_ERROR, "is-error");
      });
  }

  function postBulk(body) {
    if (!config) return;
    fetch(config.bulkUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        var out = $("ss-bulk-result");
        if (!res.ok) {
          if (out) out.textContent = (res.body && res.body.error) || "Übernehmen fehlgeschlagen";
          return;
        }
        if (out) out.textContent = res.body.applied + " Zeilen gesetzt";
        if (res.body.grid) replaceGrid(res.body.grid);
      })
      .catch(function () {
        var out = $("ss-bulk-result");
        if (out) out.textContent = "Übernehmen fehlgeschlagen";
      });
  }

  function bind() {
    var cfgEl = $("ss-grid-config");
    var el = $("ss-spreadsheet");
    statusEl = $("ss-save-status");
    if (!cfgEl || !el || typeof jspreadsheet !== "function") return;
    config = JSON.parse(cfgEl.textContent);
    replaceGrid(config);
    ["ss-filter-code", "ss-filter-prefix", "ss-filter-name", "ss-filter-match", "ss-filter-intent"].forEach(function (id) {
      var node = $(id);
      if (!node) return;
      node.addEventListener("input", applyFilters);
      node.addEventListener("change", applyFilters);
    });
    var selectBtn = $("ss-select-visible");
    if (selectBtn) selectBtn.addEventListener("click", selectVisible);
    var applyBtn = $("ss-bulk-apply");
    if (applyBtn) {
      applyBtn.addEventListener("click", function () {
        var ids = visibleSelectedIds();
        if (!ids.length) ids = visibleRowIds();
        postBulk({
          row_ids: ids,
          rabatt_1: ($("ss-bulk-r1") && $("ss-bulk-r1").value) || "",
          rabatt_2: ($("ss-bulk-r2") && $("ss-bulk-r2").value) || "",
          kein_rabatt: false,
        });
      });
    }
    var zeroBtn = $("ss-bulk-zero");
    if (zeroBtn) {
      zeroBtn.addEventListener("click", function () {
        var ids = visibleSelectedIds();
        if (!ids.length) ids = visibleRowIds();
        postBulk({ row_ids: ids, kein_rabatt: true });
      });
    }
  }

  function visibleSelectedIds() {
    if (!worksheet || !config) return [];
    var sel = worksheet.selectedCell;
    if (!sel || sel.length < 4) return [];
    var y1 = Math.min(Number(sel[1]), Number(sel[3]));
    var y2 = Math.max(Number(sel[1]), Number(sel[3]));
    var ids = [];
    for (var y = y1; y <= y2; y++) {
      if (rowIsHidden(y)) continue;
      ids.push(config.rowIds[y]);
    }
    return ids;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
