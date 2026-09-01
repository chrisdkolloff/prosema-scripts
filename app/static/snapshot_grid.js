/* Read-only snapshot grid — Jspreadsheet CE v5, no edits or formula engine. */
(function () {
  function $(id) {
    return document.getElementById(id);
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
   * CE freezes columns by setting style.left from scroll events (relative
   * positioning). That always lags. Replace with CSS sticky and turn off the
   * CE freeze updater so columns stay glued during horizontal scroll.
   */
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

    table.querySelectorAll("thead tr > td:first-child").forEach(function (td) {
      td.classList.add("jss_freezed");
      td.style.setProperty("position", "sticky", "important");
      td.style.setProperty("left", "0px", "important");
      td.style.setProperty("top", "0px", "important");
    });
    table.querySelectorAll("tbody tr > td:first-child").forEach(function (td) {
      td.classList.add("jss_freezed");
      td.style.setProperty("position", "sticky", "important");
      td.style.setProperty("left", "0px", "important");
    });

    for (var s = 0; s < n; s++) {
      var header = worksheet.headers[s];
      var last = s === n - 1;
      if (header) {
        header.classList.add("jss_freezed");
        if (last) header.classList.add("jss_freezed-edge");
        header.style.setProperty("position", "sticky", "important");
        header.style.setProperty("left", left + "px", "important");
        header.style.setProperty("top", "0px", "important");
      }
      if (worksheet.records) {
        for (var r = 0; r < worksheet.records.length; r++) {
          var cell = worksheet.records[r] && worksheet.records[r][s];
          if (cell && cell.element) {
            cell.element.classList.add("jss_freezed");
            if (last) cell.element.classList.add("jss_freezed-edge");
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

    // Prevent CE scrollControls from rewriting left on every scroll tick.
    worksheet.options.freezeColumns = 0;
  }

  function init(root) {
    var scope = root && root.querySelector ? root : document;
    var el = scope.querySelector ? scope.querySelector("#snapshot-spreadsheet") : $("snapshot-spreadsheet");
    var cfgEl = scope.querySelector ? scope.querySelector("#snapshot-grid-config") : $("snapshot-grid-config");
    if (!el || !cfgEl || typeof jspreadsheet !== "function") return;
    var config = JSON.parse(cfgEl.textContent);
    destroyExisting(el);

    var worksheets = jspreadsheet(el, {
      parseFormulas: false,
      autoCasting: false,
      autoIncrement: false,
      toolbar: false,
      about: false,
      worksheets: [
        {
          data: config.data,
          columns: config.columns,
          freezeColumns: config.freezeColumns || 1,
          filters: false,
          search: false,
          tableOverflow: true,
          tableWidth: "100%",
          tableHeight: "70vh",
          editable: false,
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
    var worksheet = worksheets && worksheets[0] ? worksheets[0] : worksheets;
    hardenFreeze(worksheet);
  }

  document.addEventListener("DOMContentLoaded", function () {
    init(document);
  });
  // outerHTML replaces the target, so event.detail.target is detached — always
  // re-init from the live panel in the document.
  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail && event.detail.target;
    var elt = event.detail && event.detail.elt;
    if (
      !(
        (target && target.id === "snapshot-grid-panel") ||
        (elt && elt.id === "snapshot-grid-panel")
      )
    ) {
      return;
    }
    var panel = document.getElementById("snapshot-grid-panel");
    if (panel) init(panel);
  });

  if (document.readyState !== "loading") {
    init(document);
  }
})();

(function () {
  var FAIL_MSG = "Die Anfrage ist fehlgeschlagen. Bitte erneut versuchen.";

  function pickExamplePlaceholder() {
    var input = document.getElementById("snapshot-frage");
    var src = document.getElementById("snapshot-frage-examples");
    if (!input || !src) return;
    var examples;
    try {
      examples = JSON.parse(src.textContent);
    } catch (err) {
      return;
    }
    if (!Array.isArray(examples) || !examples.length) return;
    var idx = Math.floor(Math.random() * examples.length);
    input.setAttribute("placeholder", examples[idx]);
  }

  function bindFrageForm() {
    var form = document.getElementById("snapshot-frage-form");
    if (!form || form.dataset.bound === "1") return;
    form.dataset.bound = "1";
    pickExamplePlaceholder();
    var btn = document.getElementById("snapshot-frage-submit");
    var input = document.getElementById("snapshot-frage");
    var status = document.getElementById("snapshot-frage-status");

    function setStatus(kind, message) {
      if (!status) return;
      status.hidden = !message;
      status.textContent = message || "";
      status.className =
        kind === "error"
          ? "alert alert-danger mt-3 mb-0"
          : "alert alert-info mt-3 mb-0";
    }

    function setBusy(busy) {
      form.dataset.busy = busy ? "1" : "0";
      document.body.classList.toggle("is-frage-busy", busy);
      if (btn) btn.disabled = busy;
      if (input) input.readOnly = busy;
      if (busy) setStatus("error", "");
    }

    form.addEventListener("submit", function (event) {
      if (form.dataset.busy === "1") {
        event.preventDefault();
        return;
      }
      var body = new FormData(form);
      setBusy(true);
      if (typeof fetch !== "function") return;

      event.preventDefault();
      fetch(form.action, {
        method: "POST",
        body: body,
        credentials: "same-origin",
        redirect: "follow",
        headers: { Accept: "text/html" },
      })
        .then(function (res) {
          if (res.redirected) {
            window.location.assign(res.url);
            return;
          }
          if (!res.ok) throw new Error("fail");
          return res.text().then(function (html) {
            document.open();
            document.write(html);
            document.close();
          });
        })
        .catch(function () {
          setBusy(false);
          setStatus("error", FAIL_MSG);
        });
    });
  }

  document.addEventListener("DOMContentLoaded", bindFrageForm);
  if (document.readyState !== "loading") {
    bindFrageForm();
  }
})();
