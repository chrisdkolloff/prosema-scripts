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

  function isQueuedField(field) {
    return field && field !== "_zeile" && field !== "_status" && field !== "Prosema Artikelnummer";
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
    var x = arguments[3];
    var y = arguments[4];
    var value = arguments[5];
    queueChange(Number(x), Number(y), value);
  }

  function colIndex(field) {
    return config.fields.indexOf(field);
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
        var numCol = colIndex("Prosema Artikelnummer");
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
  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail && event.detail.target;
    if (target && target.id === "batch-grid-panel") init(target);
  });
  window.addEventListener("blur", onBlur);
  window.addEventListener("beforeunload", onUnload);

  if (document.readyState !== "loading") {
    init(document);
  }
})();
