/* Batch grid: idle-flush queue onto POST /batches/{id}/edits. Jspreadsheet CE v5. */
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

  function isArticleNumberField(field) {
    return field === "Prosema-Artikelnummer" || field === "Prosema Artikelnummer";
  }

  function isQueuedField(field) {
    return field && field !== "_zeile" && field !== "_status" && !isArticleNumberField(field);
  }

  function encodeValue(field, value) {
    if (field === "include") {
      return value === true || value === 1 || value === "true" || value === "1";
    }
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

  function onEvent(event) {
    if (event !== "onchange") return;
    var x = Number(arguments[3]);
    var y = Number(arguments[4]);
    var value = arguments[5];
    var field = fieldAt(x);
    if (field === "Hauptgruppe") {
      syncUntergruppeForHaupt(y, value);
    }
    queueChange(x, y, value);
  }

  function cellIsReadonly(x, y) {
    var col = config.columns && config.columns[x];
    if (col && col.readOnly) return true;
    var rec = worksheet.records && worksheet.records[y] && worksheet.records[y][x];
    return !!(rec && rec.element && rec.element.classList.contains("readonly"));
  }

  function rowIsHidden(y) {
    var row = worksheet.rows && worksheet.rows[y];
    return !!(row && row.element && row.element.style.display === "none");
  }

  function fillDownFromSelection() {
    if (!worksheet || !config || !config.editable) return;
    var sel = worksheet.selectedCell;
    if (!sel || sel.length < 4) return;
    var x1 = Math.min(Number(sel[0]), Number(sel[2]));
    var x2 = Math.max(Number(sel[0]), Number(sel[2]));
    var y1 = Math.min(Number(sel[1]), Number(sel[3]));
    var y2 = Math.max(Number(sel[1]), Number(sel[3]));
    var last = worksheet.rows ? worksheet.rows.length - 1 : config.data.length - 1;
    if (y2 >= last) return;
    var patternLen = y2 - y1 + 1;
    for (var x = x1; x <= x2; x++) {
      if (!isQueuedField(fieldAt(x))) continue;
      for (var y = y2 + 1; y <= last; y++) {
        if (rowIsHidden(y) || cellIsReadonly(x, y)) continue;
        var srcY = y1 + ((y - (y2 + 1)) % patternLen);
        var value = worksheet.getValueFromCoords(x, srcY);
        var current = worksheet.getValueFromCoords(x, y);
        if (value == null) value = "";
        if (current == null) current = "";
        if (String(current) === String(value)) continue;
        worksheet.setValueFromCoords(x, y, value);
        if (fieldAt(x) === "Hauptgruppe") syncUntergruppeForHaupt(y, value);
      }
    }
  }

  function onCornerDblClick(event) {
    if (!event.target || !event.target.classList.contains("jss_corner")) return;
    event.preventDefault();
    event.stopPropagation();
    fillDownFromSelection();
  }

  function bindFillHandle(el) {
    if (!el) return;
    el.removeEventListener("dblclick", onCornerDblClick, true);
    el.addEventListener("dblclick", onCornerDblClick, true);
  }

  function colIndex(field) {
    return config.fields.indexOf(field);
  }

  function untergruppeOptionsForHaupt(hauptLabel) {
    var map = (config && config.untergruppeByHauptgruppe) || {};
    var kids = map[hauptLabel] || [];
    return [""].concat(kids);
  }

  function syncUntergruppeForHaupt(y, hauptValue) {
    if (applying || !worksheet || !config || !config.editable) return;
    var unterIdx = colIndex("Untergruppe");
    if (unterIdx < 0) return;
    var allowed = untergruppeOptionsForHaupt(String(hauptValue == null ? "" : hauptValue));
    var current = worksheet.getValueFromCoords(unterIdx, y);
    var cur = current == null ? "" : String(current);
    if (!cur || allowed.indexOf(cur) >= 0) return;
    applying = true;
    try {
      worksheet.setValueFromCoords(unterIdx, y, "", true);
    } finally {
      applying = false;
    }
    queueChange(unterIdx, y, "");
  }

  function attachUntergruppeFilter(columns) {
    if (!config || !columns) return;
    var unterIdx = colIndex("Untergruppe");
    var hauptIdx = colIndex("Hauptgruppe");
    if (unterIdx < 0 || !columns[unterIdx]) return;
    columns[unterIdx].filter = function (_el, _cell, _x, y) {
      var haupt = "";
      if (worksheet && typeof worksheet.getValueFromCoords === "function" && hauptIdx >= 0) {
        var live = worksheet.getValueFromCoords(hauptIdx, y);
        haupt = live == null ? "" : String(live);
      } else if (config.data && config.data[y]) {
        haupt = String(config.data[y][hauptIdx] || "");
      }
      return untergruppeOptionsForHaupt(haupt);
    };
  }

  function applyRowState(y, include, error) {
    if (!worksheet || !worksheet.rows || !worksheet.rows[y]) return;
    var tr = worksheet.rows[y].element;
    if (!tr) return;
    tr.classList.toggle("batch-row-error", !!error);
    tr.classList.toggle("batch-row-excluded", include === false);
  }

  function applyServerRows(rows) {
    if (!worksheet || !rows) return;
    applying = true;
    try {
      for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        var y = config.rowIds.indexOf(row.id);
        if (y < 0) continue;
        var numCol = colIndex("Prosema-Artikelnummer");
        if (numCol < 0) numCol = colIndex("Prosema Artikelnummer");
        var statusCol = colIndex("_status");
        var includeCol = colIndex("include");
        if (numCol >= 0) {
          worksheet.setValueFromCoords(numCol, y, row.proposed_article_number || "", true);
        }
        if (statusCol >= 0) {
          worksheet.setValueFromCoords(statusCol, y, row.validation_error || "", true);
        }
        if (includeCol >= 0 && typeof row.include === "boolean") {
          worksheet.setValueFromCoords(includeCol, y, row.include, true);
        }
        var corrected = row.corrected || {};
        Object.keys(corrected).forEach(function (field) {
          var x = colIndex(field);
          if (x >= 0) worksheet.setValueFromCoords(x, y, corrected[field], true);
        });
        applyRowState(y, row.include, row.validation_error);
        if (config.rowState[y]) {
          config.rowState[y].include = row.include;
          config.rowState[y].validation_error = row.validation_error || "";
        }
      }
    } finally {
      applying = false;
    }
  }

  function paintInitial() {
    if (!config || !config.rowState) return;
    for (var y = 0; y < config.rowState.length; y++) {
      var state = config.rowState[y];
      applyRowState(y, state.include, state.validation_error);
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

    function succeed(data, options) {
      flushing = false;
      applyServerRows(data && data.rows);
      if (!(options && options.skipActionBar)) {
        refreshActionBar();
      }
      if (queue.length) {
        setStatus(STATUS_SAVING, "is-saving");
        scheduleFlush();
      } else {
        setStatus(STATUS_SAVED, "is-saved");
      }
    }

    function refreshActionBar() {
      if (!config || !config.actionsUrl) return;
      fetch(config.actionsUrl, {
        method: "GET",
        headers: { Accept: "text/html" },
        credentials: "same-origin",
      })
        .then(function (response) {
          if (!response.ok) return null;
          return response.text();
        })
        .then(function (html) {
          if (!html) return;
          var bar = document.getElementById("batch-action-bar");
          if (!bar || !bar.parentNode) return;
          var tmp = document.createElement("div");
          tmp.innerHTML = html.trim();
          var next = tmp.firstElementChild;
          if (next) bar.parentNode.replaceChild(next, bar);
          var scope = document.getElementById("batch-action-bar");
          if (scope && window.htmx) {
            htmx.process(scope);
          }
          if (scope && window.coreui && coreui.Modal) {
            scope.querySelectorAll('[data-coreui-toggle="modal"]').forEach(function (el) {
              coreui.Modal.getOrCreateInstance(el);
            });
          }
        })
        .catch(function () {
          /* leave the bar as-is; next save retries */
        });
    }

    if (keepalive && navigator.sendBeacon) {
      var blob = new Blob([body], { type: "application/json" });
      if (!navigator.sendBeacon(url, blob)) fail();
      else succeed({ rows: [] }, { skipActionBar: true });
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

  /** CSS sticky freeze — CE's scrollLeft→style.left updater lags. */
  function hardenFreeze(worksheet) {
    var n = Number(worksheet && worksheet.options && worksheet.options.freezeColumns) || 0;
    if (!n || !worksheet.headers) return;

    var table =
      worksheet.table ||
      (worksheet.element && worksheet.element.querySelector
        ? worksheet.element.querySelector("table")
        : null);
    if (!table) return;

    var nest = table.querySelector("thead tr > td:first-child");
    var left = nest ? nest.offsetWidth : 50;

    table.querySelectorAll("thead tr > td:first-child, tbody tr > td:first-child").forEach(function (td) {
      td.classList.add("jss_freezed");
      td.style.setProperty("position", "sticky", "important");
      td.style.setProperty("left", "0px", "important");
    });

    for (var s = 0; s < n; s++) {
      var header = worksheet.headers[s];
      if (header) {
        header.classList.add("jss_freezed");
        header.style.setProperty("position", "sticky", "important");
        header.style.setProperty("left", left + "px", "important");
      }
      if (worksheet.records) {
        for (var r = 0; r < worksheet.records.length; r++) {
          var cell = worksheet.records[r] && worksheet.records[r][s];
          if (cell && cell.element) {
            cell.element.classList.add("jss_freezed");
            cell.element.style.setProperty("position", "sticky", "important");
            cell.element.style.setProperty("left", left + "px", "important");
          }
        }
      }
      var width = 100;
      if (worksheet.options.columns && worksheet.options.columns[s] && worksheet.options.columns[s].width) {
        width = parseInt(worksheet.options.columns[s].width, 10) || 100;
      } else if (header && header.offsetWidth) {
        width = header.offsetWidth;
      }
      left += width;
    }

    worksheet.options.freezeColumns = 0;
  }

  function init(root) {
    var scope = root && root.querySelector ? root : document;
    var el = scope.querySelector ? scope.querySelector("#batch-spreadsheet") : $("batch-spreadsheet");
    var cfgEl = scope.querySelector ? scope.querySelector("#batch-grid-config") : $("batch-grid-config");
    statusEl = scope.querySelector ? scope.querySelector("#batch-save-status") : $("batch-save-status");
    if (!el || !cfgEl || typeof jspreadsheet !== "function") return;
    config = JSON.parse(cfgEl.textContent);
    queue = [];
    flushing = false;
    destroyExisting(el);
    attachUntergruppeFilter(config.columns);

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
          freezeColumns: config.freezeColumns || 3,
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
    bindFillHandle(el);
    paintInitial();
    if (statusEl && !statusEl.textContent) setStatus(STATUS_SAVED, "is-saved");
  }

  function onBlur() {
    flush(false);
  }

  function onUnload() {
    flush(true);
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
        (target && target.id === "batch-grid-panel") ||
        (elt && elt.id === "batch-grid-panel")
      )
    ) {
      return;
    }
    var panel = document.getElementById("batch-grid-panel");
    if (panel) init(panel);
  });
  window.addEventListener("blur", onBlur);
  window.addEventListener("beforeunload", onUnload);

  if (document.readyState !== "loading") {
    init(document);
  }
})();
