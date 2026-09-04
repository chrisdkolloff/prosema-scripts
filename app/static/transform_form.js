/* Transform spec builder on the Artikelübersicht. No extra libraries. */
(function () {
  function $(id) {
    return document.getElementById(id);
  }

  function labels() {
    var el = $("transform-op-labels");
    if (!el) return {};
    try {
      return JSON.parse(el.textContent);
    } catch (err) {
      return {};
    }
  }

  function messages() {
    var el = $("transform-op-messages");
    if (!el) return {};
    try {
      return JSON.parse(el.textContent);
    } catch (err) {
      return {};
    }
  }

  function escapeRe(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function wordStillMatches(search, replace) {
    if (!search) return false;
    var re;
    try {
      re = new RegExp("(?<![A-Za-zÄÖÜäöüß-])" + escapeRe(search) + "(?![A-Za-zÄÖÜäöüß-])", "i");
    } catch (err) {
      return false;
    }
    return replace.replace(re, replace) !== replace;
  }

  function validateOp(li, msgs) {
    var kind = li.querySelector(".transform-op-kind");
    var search = li.querySelector(".transform-op-search");
    var replace = li.querySelector(".transform-op-replace");
    var searchMsg = li.querySelector(".transform-op-search-msg");
    var warn = li.querySelector(".transform-op-warn");
    var wrap = li.querySelector(".transform-op-replace-wrap");
    var needsReplace = kind.value === "replace_word" || kind.value === "replace_literal";
    wrap.hidden = !needsReplace;
    search.classList.remove("is-invalid");
    searchMsg.textContent = "";
    warn.hidden = true;
    warn.textContent = "";
    var s = search.value;
    var r = replace.value;
    if (s === "") {
      search.classList.add("is-invalid");
      searchMsg.textContent = msgs.empty || "";
      return false;
    }
    if (s.indexOf("&") >= 0) {
      search.classList.add("is-invalid");
      searchMsg.textContent = msgs.amp || "";
      return false;
    }
    if (needsReplace && s === r) {
      search.classList.add("is-invalid");
      searchMsg.textContent = msgs.noop || "";
      return false;
    }
    if (needsReplace && msgs.non_idem) {
      var fires = false;
      if (kind.value === "replace_literal" && r.indexOf(s) >= 0) fires = true;
      if (kind.value === "replace_word" && wordStillMatches(s, r)) fires = true;
      if (fires) {
        warn.hidden = false;
        warn.textContent = msgs.non_idem.replace("{search}", s).replace("{replace}", r);
      }
    }
    return true;
  }

  function renumber(list) {
    var items = list.querySelectorAll(".transform-op");
    items.forEach(function (li, i) {
      var num = li.querySelector(".transform-op-num");
      if (num) num.textContent = String(i + 1) + ".";
    });
  }

  function fillKind(select, labs) {
    Array.prototype.forEach.call(select.options, function (opt) {
      opt.textContent = labs[opt.value] || opt.value;
    });
  }

  function addOp(list, template, labs, msgs) {
    var node = template.content.firstElementChild.cloneNode(true);
    fillKind(node.querySelector(".transform-op-kind"), labs);
    list.appendChild(node);
    bindOp(node, list, template, labs, msgs);
    renumber(list);
    validateOp(node, msgs);
  }

  function bindOp(li, list, template, labs, msgs) {
    li.querySelector(".transform-op-kind").addEventListener("change", function () {
      validateOp(li, msgs);
    });
    li.querySelector(".transform-op-search").addEventListener("input", function () {
      validateOp(li, msgs);
    });
    li.querySelector(".transform-op-replace").addEventListener("input", function () {
      validateOp(li, msgs);
    });
    li.querySelector(".transform-op-remove").addEventListener("click", function () {
      if (list.querySelectorAll(".transform-op").length < 2) return;
      li.remove();
      renumber(list);
    });
    li.querySelector(".transform-op-up").addEventListener("click", function () {
      if (li.previousElementSibling) list.insertBefore(li, li.previousElementSibling);
      renumber(list);
    });
    li.querySelector(".transform-op-down").addEventListener("click", function () {
      if (li.nextElementSibling) list.insertBefore(li.nextElementSibling, li);
      renumber(list);
    });
  }

  function selectedArticleNumbers() {
    var root = $("snapshot-spreadsheet");
    if (!root || typeof jspreadsheet === "undefined") return [];
    var worksheet = root.jspreadsheet || (root.jexcel && root.jexcel);
    if (!worksheet && root.children && root.children[0]) {
      worksheet = root.children[0].jspreadsheet || root.children[0].jexcel;
    }
    var cfg = $("snapshot-grid-config");
    var fields = [];
    try {
      fields = JSON.parse(cfg.textContent).fields || [];
    } catch (err) {
      return [];
    }
    var idx = fields.indexOf("Prosema-Artikelnummer");
    if (idx < 0) idx = 0;
    var selected = [];
    try {
      var ws = jspreadsheet.current || worksheet;
      if (ws && typeof ws.getSelectedRows === "function") {
        var rows = ws.getSelectedRows(true) || [];
        rows.forEach(function (row) {
          var data = ws.getRowData ? ws.getRowData(row) : null;
          if (data && data[idx]) selected.push(String(data[idx]));
        });
      }
    } catch (err) {
      return [];
    }
    return selected;
  }

  function bind() {
    var form = $("transform-spec-form");
    var list = $("transform-ops");
    var template = $("transform-op-template");
    if (!form || !list || !template) return;
    var labs = labels();
    var msgs = messages();
    var addBtn = $("transform-op-add");
    if (addBtn) {
      addBtn.addEventListener("click", function () {
        addOp(list, template, labs, msgs);
      });
    }
    if (!list.querySelector(".transform-op")) addOp(list, template, labs, msgs);
    form.addEventListener("submit", function (event) {
      var ok = true;
      list.querySelectorAll(".transform-op").forEach(function (li) {
        if (!validateOp(li, msgs)) ok = false;
      });
      if (!ok) {
        event.preventDefault();
        return;
      }
      var box = $("transform-selected-numbers");
      box.innerHTML = "";
      selectedArticleNumbers().forEach(function (num) {
        var input = document.createElement("input");
        input.type = "hidden";
        input.name = "artikelnummer";
        input.value = num;
        box.appendChild(input);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", bind);
  if (document.readyState !== "loading") bind();
})();
