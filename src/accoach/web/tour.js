"use strict";
// HONE guided tour — a tiny, reusable coachmark overlay.
// Vanilla JS, 100% offline: no CDN, no libraries, no build step.
//
//   startTour(steps, storageKey)   steps = [{sel, title, text}, ...]
//   HoneTour.start(steps, key)     same thing, namespaced
//   HoneTour.auto(steps, key)      starts only on first visit (key absent)
//
// `sel` is a CSS selector for the element to highlight. Steps whose target is
// missing or not visible are skipped defensively. The whole thing is one
// overlay layer that never touches the page's own DOM (no canvas interference).
(function () {
  var PAD = 6;          // breathing room around the highlighted target
  var GAP = 12;         // distance between target and the tooltip card
  var styleInjected = false;
  var closeCurrent = null;   // teardown of the tour currently on screen, if any

  function injectStyle() {
    if (styleInjected) return;
    styleInjected = true;
    var css =
      ".hone-tour-root{position:fixed;inset:0;z-index:99999;" +
      "font-family:var(--font-ui,'Inter',system-ui,'Segoe UI',sans-serif);}" +
      ".hone-tour-backdrop{position:fixed;inset:0;background:transparent;cursor:pointer;}" +
      ".hone-tour-hole{position:fixed;border:2px solid #22D3CE;border-radius:10px;" +
      "box-shadow:0 0 0 9999px rgba(7,10,14,0.66),0 0 18px rgba(34,211,206,0.55);" +
      "pointer-events:none;transition:left .18s ease,top .18s ease,width .18s ease,height .18s ease;}" +
      ".hone-tour-card{position:fixed;max-width:320px;background:#151A21;border:1px solid #232B35;" +
      "border-radius:14px;padding:16px 18px;box-shadow:0 14px 44px rgba(0,0,0,.55);" +
      "color:#E8EDF2;pointer-events:auto;}" +
      ".hone-tour-card h4{margin:0 0 6px;font-size:16px;font-weight:600;color:#E8EDF2;" +
      "font-family:var(--font-display,'Space Grotesk',system-ui,'Segoe UI',sans-serif);}" +
      ".hone-tour-card p{margin:0 0 14px;font-size:13px;line-height:1.5;color:#8A95A3;}" +
      ".hone-tour-foot{display:flex;align-items:center;gap:8px;}" +
      ".hone-tour-count{font-size:12px;color:#8A95A3;margin-right:auto;" +
      "font-family:var(--font-mono,ui-monospace,Consolas,monospace);}" +
      ".hone-tour-btn{background:#0B0E12;color:#E8EDF2;border:1px solid #232B35;border-radius:8px;" +
      "padding:7px 14px;font-size:13px;cursor:pointer;font-family:inherit;}" +
      ".hone-tour-btn:hover{border-color:#22D3CE;color:#22D3CE;}" +
      ".hone-tour-btn[disabled]{opacity:.4;cursor:default;}" +
      ".hone-tour-btn[disabled]:hover{border-color:#232B35;color:#E8EDF2;}" +
      ".hone-tour-btn.primary{background:#22D3CE;color:#0B0E12;border-color:#22D3CE;font-weight:600;}" +
      ".hone-tour-btn.primary:hover{background:#34E08A;border-color:#34E08A;color:#0B0E12;}";
    var el = document.createElement("style");
    el.id = "hone-tour-style";
    el.textContent = css;
    document.head.appendChild(el);
  }

  function elFor(step) {
    if (!step || !step.sel) return null;
    try { return document.querySelector(step.sel); } catch (e) { return null; }
  }

  function visible(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    var cs = window.getComputedStyle(el);
    return cs.display !== "none" && cs.visibility !== "hidden";
  }

  function startTour(steps, storageKey) {
    if (!Array.isArray(steps) || !steps.length) return;
    if (typeof closeCurrent === "function") closeCurrent();   // one tour at a time
    injectStyle();

    // Steps that actually have a visible target right now (defensive skip).
    function showable() {
      var out = [];
      for (var i = 0; i < steps.length; i++) {
        var el = elFor(steps[i]);
        if (el && visible(el)) out.push(i);
      }
      return out;
    }

    var list = showable();
    if (!list.length) return;        // nothing to point at — quietly do nothing
    var cursor = list[0];
    var active = true;
    var raf = 0;

    var root = document.createElement("div");
    root.className = "hone-tour-root";
    var backdrop = document.createElement("div");
    backdrop.className = "hone-tour-backdrop";
    var hole = document.createElement("div");
    hole.className = "hone-tour-hole";
    var card = document.createElement("div");
    card.className = "hone-tour-card";
    root.appendChild(backdrop);
    root.appendChild(hole);
    root.appendChild(card);
    document.body.appendChild(root);

    function finish() {
      if (!active) return;
      active = false;
      closeCurrent = null;
      window.removeEventListener("resize", onReflow, true);
      window.removeEventListener("scroll", onReflow, true);
      document.removeEventListener("keydown", onKey, true);
      if (root.parentNode) root.parentNode.removeChild(root);
      try { if (storageKey) localStorage.setItem(storageKey, "1"); } catch (e) {}
    }
    closeCurrent = finish;

    function place(el) {
      var r = el.getBoundingClientRect();
      var vw = window.innerWidth, vh = window.innerHeight;
      var px = Math.max(0, r.left - PAD), py = Math.max(0, r.top - PAD);
      var pw = Math.min(vw, r.right + PAD) - px;
      var ph = Math.min(vh, r.bottom + PAD) - py;
      hole.style.left = px + "px";
      hole.style.top = py + "px";
      hole.style.width = pw + "px";
      hole.style.height = ph + "px";

      var cw = card.offsetWidth, ch = card.offsetHeight;
      var top = r.bottom + GAP;
      if (top + ch > vh - 8) top = r.top - GAP - ch;   // not enough room below → above
      if (top < 8) top = 8;                            // target taller than viewport
      var left = r.left;
      if (left + cw > vw - 8) left = vw - 8 - cw;
      if (left < 8) left = 8;
      card.style.top = top + "px";
      card.style.left = left + "px";
    }

    function render() {
      list = showable();
      if (!list.length) { finish(); return; }
      if (list.indexOf(cursor) === -1) cursor = list[0];
      var pos = list.indexOf(cursor);
      var step = steps[cursor];
      var el = elFor(step);
      if (!el) { finish(); return; }

      var last = pos === list.length - 1;
      card.innerHTML = "";
      var h = document.createElement("h4");
      h.textContent = step.title || "";
      var p = document.createElement("p");
      p.textContent = step.text || "";
      var foot = document.createElement("div");
      foot.className = "hone-tour-foot";
      var count = document.createElement("span");
      count.className = "hone-tour-count";
      count.textContent = "Step " + (pos + 1) + "/" + list.length;
      var skip = mkBtn("Skip", false, finish);
      var back = mkBtn("Back", false, function () { go(-1); });
      back.disabled = pos === 0;
      var next = mkBtn(last ? "Done" : "Next", true, function () { go(1); });
      foot.appendChild(count);
      foot.appendChild(skip);
      foot.appendChild(back);
      foot.appendChild(next);
      card.appendChild(h);
      card.appendChild(p);
      card.appendChild(foot);

      try { el.scrollIntoView({ block: "center", inline: "nearest" }); } catch (e) {}
      place(el);
    }

    function mkBtn(label, primary, fn) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "hone-tour-btn" + (primary ? " primary" : "");
      b.textContent = label;
      b.addEventListener("click", function (e) { e.stopPropagation(); fn(); });
      return b;
    }

    function go(dir) {
      list = showable();
      if (!list.length) { finish(); return; }
      var pos = list.indexOf(cursor);
      if (pos === -1) pos = 0;
      var np = pos + dir;
      if (np < 0) np = 0;
      if (np >= list.length) { finish(); return; }   // "Done" past the last step
      cursor = list[np];
      render();
    }

    function onReflow() {
      if (!active) return;
      if (raf) return;
      raf = window.requestAnimationFrame(function () {
        raf = 0;
        if (!active) return;
        var el = elFor(steps[cursor]);
        if (el && visible(el)) place(el);
        else render();
      });
    }

    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); finish(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
    }

    backdrop.addEventListener("click", finish);
    window.addEventListener("resize", onReflow, true);
    window.addEventListener("scroll", onReflow, true);
    document.addEventListener("keydown", onKey, true);

    render();
  }

  function autoTour(steps, storageKey) {
    try { if (storageKey && localStorage.getItem(storageKey)) return; }
    catch (e) { return; }
    startTour(steps, storageKey);
  }

  window.startTour = startTour;
  window.HoneTour = { start: startTour, auto: autoTour };
})();
