/* Shared Jspreadsheet CE freeze — CSS sticky, same as Artikelübersicht 1.1.10.
 *
 * CE freezes columns by writing style.left from scroll events (relative
 * positioning). That lags. Replace with position:sticky and disable the CE
 * freeze updater.
 *
 * Never enable CE freezeColumns so the hardcoded -51 updater does not run.
 * hideIndex (Bezugsquellen / supply export) drops the nest/# column so the
 * first frozen data column sticks at left:0.
 */
(function (global) {
  function destroy(el) {
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

  function columnWidth(worksheet, index) {
    var cols = worksheet.options && worksheet.options.columns;
    if (cols && cols[index] && cols[index].width) {
      return parseInt(cols[index].width, 10) || 100;
    }
    var header = worksheet.headers && worksheet.headers[index];
    if (header && header.offsetWidth) return header.offsetWidth;
    return 100;
  }

  function nestWidth(table) {
    var nest =
      table.querySelector("thead td.jss_selectall") ||
      table.querySelector("thead td.jss_row") ||
      table.querySelector("thead tr > td:first-child");
    if (nest && nest.offsetWidth) return nest.offsetWidth;
    return 0;
  }

  function pinSticky(el, leftPx, topPx) {
    el.style.setProperty("position", "sticky", "important");
    el.style.setProperty("left", leftPx + "px", "important");
    if (topPx != null) {
      el.style.setProperty("top", topPx + "px", "important");
    }
    el.style.removeProperty("transform");
    el.style.removeProperty("--jss-freeze-off");
    el.style.removeProperty("--jss-freeze-x");
  }

  function hardenFreeze(worksheet, options) {
    options = options || {};
    var n = Number(options.freezeColumns);
    if (!n && worksheet && worksheet.options) {
      n = Number(worksheet.options.freezeColumns) || 0;
    }
    if (!worksheet || !worksheet.options) return;
    // Kill CE's scroll-driven left updater before we touch layout.
    worksheet.options.freezeColumns = 0;
    worksheet.updateFreezePosition = function () {};
    if (!n || !worksheet.headers) return;

    var table =
      worksheet.table ||
      (worksheet.element && worksheet.element.querySelector
        ? worksheet.element.querySelector("table")
        : null);
    if (!table) return;

    if (options.hideIndex) {
      if (typeof worksheet.hideIndex === "function") {
        worksheet.hideIndex();
      } else {
        table.classList.add("jss_hidden_index");
      }
    }

    var left = options.hideIndex ? 0 : nestWidth(table);
    var s;

    if (!options.hideIndex && left) {
      table.querySelectorAll("thead td.jss_selectall, thead td.jss_row, thead tr > td:first-child").forEach(function (td) {
        td.classList.add("jss_freezed");
        pinSticky(td, 0, 0);
      });
      table.querySelectorAll("tbody td.jss_selectall, tbody td.jss_row, tbody tr > td:first-child").forEach(function (td) {
        td.classList.add("jss_freezed");
        pinSticky(td, 0);
      });
    }

    for (s = 0; s < n; s++) {
      var last = s === n - 1;
      var width = columnWidth(worksheet, s);
      var header = worksheet.headers[s];
      if (header) {
        header.classList.add("jss_freezed");
        if (last) header.classList.add("jss_freezed-edge");
        pinSticky(header, left, 0);
        header.style.setProperty("min-width", width + "px", "important");
        header.style.setProperty("max-width", width + "px", "important");
      }
      table.querySelectorAll('thead [data-x="' + s + '"]').forEach(function (td) {
        if (td === header) return;
        td.classList.add("jss_freezed");
        if (last) td.classList.add("jss_freezed-edge");
        pinSticky(td, left, 0);
      });
      if (worksheet.records) {
        for (var r = 0; r < worksheet.records.length; r++) {
          var cell = worksheet.records[r] && worksheet.records[r][s];
          if (cell && cell.element) {
            cell.element.classList.add("jss_freezed");
            if (last) cell.element.classList.add("jss_freezed-edge");
            pinSticky(cell.element, left);
            cell.element.style.setProperty("min-width", width + "px", "important");
            cell.element.style.setProperty("max-width", width + "px", "important");
          }
        }
      }
      if (worksheet.cols && worksheet.cols[s] && worksheet.cols[s].colElement) {
        worksheet.cols[s].colElement.setAttribute("width", String(width));
        worksheet.cols[s].colElement.style.setProperty("width", width + "px", "important");
      }
      left += width;
    }

    var headerH = 0;
    if (worksheet.headers[0] && worksheet.headers[0].offsetHeight) {
      headerH = worksheet.headers[0].offsetHeight;
    }
    table.querySelectorAll("thead tr:nth-child(2) [data-x]").forEach(function (td) {
      if (headerH) td.style.setProperty("top", headerH + "px", "important");
    });
  }

  global.ProsemaSpreadsheet = {
    destroy: destroy,
    hardenFreeze: hardenFreeze,
  };
})(window);
