/* Preview table: scroll-to-end unlocks confirm; group select all. */
(function () {
  function $(id) {
    return document.getElementById(id);
  }

  function atEnd(el) {
    return el.scrollTop + el.clientHeight >= el.scrollHeight - 4;
  }

  function bind() {
    var viewport = $("transform-review-viewport");
    var confirm = $("transform-confirm");
    if (viewport && confirm) {
      if (viewport.scrollHeight <= viewport.clientHeight + 4) {
        confirm.disabled = false;
      }
      var unlocked = false;
      viewport.addEventListener("scroll", function () {
        if (unlocked) return;
        if (atEnd(viewport)) {
          unlocked = true;
          confirm.disabled = false;
        }
      });
    }
    document.querySelectorAll(".transform-group-all").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var group = btn.getAttribute("data-group");
        var on = btn.getAttribute("data-on") === "1";
        document.querySelectorAll('.transform-row-check[data-group="' + group + '"]').forEach(function (box) {
          box.checked = on;
        });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", bind);
  if (document.readyState !== "loading") bind();
})();
