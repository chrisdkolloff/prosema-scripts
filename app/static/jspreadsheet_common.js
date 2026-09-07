/* Shared Jspreadsheet CE freeze — same mechanism as Artikelübersicht.
 *
 * Do not use position:sticky with a non-zero left on table cells. That is why
 * a frozen article number slides with the scroll and only "sticks" at the end.
 *
 * When the nest/# column is hidden, the first data column is at left:0 and
 * can use sticky with no per-scroll work (no lag). Extra frozen columns and
 * a visible nest still use one CSS variable + transform instead of writing
 * style.left on every body cell.
 *
 * Never enable CE freezeColumns so the hardcoded -51 updater does not run.
 */
(function (global) {
  var FREEZE_TX =
    "translate3d(calc(var(--jss-freeze-x, 0px) + var(--jss-freeze-off, 0px)), 0, 0)";

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
      table.querySelector("thead td.jss_row");
    if (nest && nest.offsetWidth) return nest.offsetWidth;
    return 0;
  }

  function eachFrozen(worksheet, table, s, fn) {
    var header = worksheet.headers && worksheet.headers[s];
    if (header) fn(header, true);
    table.querySelectorAll('thead [data-x="' + s + '"]').forEach(function (td) {
      fn(td, true);
    });
    if (!worksheet.records) return;
    for (var r = 0; r < worksheet.records.length; r++) {
      var cell = worksheet.records[r] && worksheet.records[r][s];
      if (cell && cell.element) fn(cell.element, false);
    }
  }

  function pinSticky(el, leftPx) {
    el.style.setProperty("position", "sticky", "important");
    el.style.setProperty("left", leftPx + "px", "important");
    el.style.removeProperty("transform");
  }

  function pinTranslate(el, off) {
    el.style.setProperty("position", "relative", "important");
    el.style.left = "0px";
    el.style.setProperty("--jss-freeze-off", off + "px");
    el.style.setProperty("transform", FREEZE_TX, "important");
  }

  function hardenFreeze(worksheet, options) {
    options = options || {};
    var n = Number(options.freezeColumns);
    if (!n && worksheet && worksheet.options) {
      n = Number(worksheet.options.freezeColumns) || 0;
    }
    if (!worksheet || !worksheet.options) return;
    worksheet.options.freezeColumns = 0;
    worksheet.updateFreezePosition = function () {};
    if (!n || !worksheet.headers) return;

    var table =
      worksheet.table ||
      (worksheet.element && worksheet.element.querySelector
        ? worksheet.element.querySelector("table")
        : null);
    var content = worksheet.content;
    if (!table || !content) return;

    if (options.hideIndex) {
      if (typeof worksheet.hideIndex === "function") {
        worksheet.hideIndex();
      } else {
        table.classList.add("jss_hidden_index");
      }
    }

    var nest = options.hideIndex ? 0 : nestWidth(table);
    var offsets = [];
    var acc = nest;
    var s;
    for (s = 0; s < n; s++) {
      offsets[s] = acc;
      acc += columnWidth(worksheet, s);
    }

    if (nest) {
      table.querySelectorAll("thead td.jss_selectall, thead td.jss_row").forEach(function (td) {
        td.classList.add("jss_freezed");
        pinSticky(td, 0);
      });
      table.querySelectorAll("tbody td.jss_selectall, tbody td.jss_row").forEach(function (td) {
        td.classList.add("jss_freezed");
        pinTranslate(td, 0);
      });
    }

    var needsScrollSync = !!nest;
    for (s = 0; s < n; s++) {
      var last = s === n - 1;
      var width = columnWidth(worksheet, s);
      var stickyBody = nest === 0 && offsets[s] === 0;
      if (!stickyBody) needsScrollSync = true;
      eachFrozen(worksheet, table, s, function (el, isHeader) {
        el.classList.add("jss_freezed");
        if (last) el.classList.add("jss_freezed-edge");
        el.style.setProperty("min-width", width + "px", "important");
        el.style.setProperty("max-width", width + "px", "important");
        if (isHeader || stickyBody) {
          pinSticky(el, offsets[s]);
        } else {
          pinTranslate(el, offsets[s]);
        }
      });
      if (worksheet.cols && worksheet.cols[s] && worksheet.cols[s].colElement) {
        worksheet.cols[s].colElement.setAttribute("width", String(width));
        worksheet.cols[s].colElement.style.setProperty("width", width + "px", "important");
      }
    }

    var headerH = 0;
    if (worksheet.headers[0] && worksheet.headers[0].offsetHeight) {
      headerH = worksheet.headers[0].offsetHeight;
    }
    table.querySelectorAll("thead tr:nth-child(2) [data-x]").forEach(function (td) {
      if (headerH) td.style.setProperty("top", headerH + "px", "important");
    });

    if (!needsScrollSync) return;

    var ticking = false;
    function apply() {
      ticking = false;
      table.style.setProperty("--jss-freeze-x", (content.scrollLeft || 0) + "px");
    }

    content.addEventListener(
      "scroll",
      function () {
        if (!ticking) {
          ticking = true;
          window.requestAnimationFrame(apply);
        }
      },
      { passive: true }
    );
    apply();
  }

  global.ProsemaSpreadsheet = {
    destroy: destroy,
    hardenFreeze: hardenFreeze,
  };
})(window);
