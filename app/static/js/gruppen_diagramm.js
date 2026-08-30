(function () {
  function bind(root) {
    var svg = root.querySelector(".sunburst");
    if (!svg) return;
    var idle = svg.querySelector("#sunburst-idle");
    var detail = svg.querySelector("#sunburst-detail");
    var codeEl = svg.querySelector("#sunburst-detail-code");
    var nameEl = svg.querySelector("#sunburst-detail-name");
    var ctxEl = svg.querySelector("#sunburst-detail-context");
    if (!idle || !detail || !codeEl || !nameEl || !ctxEl) return;
    function show(path) {
      codeEl.textContent = path.getAttribute("data-code") || "";
      nameEl.textContent = path.getAttribute("data-name") || "";
      ctxEl.textContent = path.getAttribute("data-context") || "";
      idle.setAttribute("visibility", "hidden");
      detail.setAttribute("visibility", "visible");
    }
    function hide() {
      detail.setAttribute("visibility", "hidden");
      idle.setAttribute("visibility", "visible");
    }
    svg.querySelectorAll("path[data-code]").forEach(function (path) {
      path.addEventListener("mouseenter", function () { show(path); });
    });
    svg.addEventListener("mouseleave", hide);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { bind(document); });
  } else {
    bind(document);
  }
})();
