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
          freezeColumns: config.freezeColumns || 2,
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
