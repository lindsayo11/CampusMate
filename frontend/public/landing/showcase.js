/* A progressive, scroll-selected story. Native scrolling is never intercepted. */
(() => {
  "use strict";
  const story = document.querySelector(".journey");
  if (!story) return;
  const root = document.documentElement;
  const frame = story.querySelector(".journey-frame");
  const panels = [...story.querySelectorAll(".journey-panel")];
  const links = [...story.querySelectorAll("[data-journey-link]")];
  const caption = story.querySelector("[data-journey-caption]");
  const captions = ["01 / 原文资料库", "02 / 发展方向", "03 / 行动计划"];
  const desktop = window.matchMedia("(min-width: 1000px) and (min-height: 700px)");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  let enhanced = false;
  let active = -1;
  let inView = false;
  let pending = 0;

  function navHeight() { return document.querySelector("header.nav")?.offsetHeight || 72; }
  function activate(index) {
    if (index === active) return;
    const focusedPanel = panels.find(panel => panel.contains(document.activeElement));
    active = index;
    story.dataset.active = String(index);
    panels.forEach((panel, i) => {
      panel.inert = enhanced && i !== index;
      if (enhanced && i !== index) panel.setAttribute("aria-hidden", "true");
      else panel.removeAttribute("aria-hidden");
    });
    links.forEach((link, i) => {
      if (enhanced && i === index) link.setAttribute("aria-current", "step");
      else link.removeAttribute("aria-current");
    });
    caption.textContent = captions[index];
    if (enhanced && focusedPanel && focusedPanel !== panels[index]) links[index].focus({ preventScroll: true });
  }
  function update() {
    pending = 0;
    if (!enhanced || document.visibilityState === "hidden") return;
    const distance = Math.max(1, story.offsetHeight - frame.offsetHeight);
    const progress = Math.min(1, Math.max(0, (navHeight() - story.getBoundingClientRect().top) / distance));
    story.style.setProperty("--journey-progress", String(progress));
    activate(Math.min(panels.length - 1, Math.floor(progress * panels.length)));
  }
  function schedule() {
    if (enhanced && inView && !pending && document.visibilityState === "visible") pending = requestAnimationFrame(update);
  }
  function setMode() {
    const next = desktop.matches && !reduced.matches && root.dataset.cmMotion === "on";
    if (next === enhanced) { story.dataset.enhanced = String(next); return; }
    const bounds = story.getBoundingClientRect();
    const keepPlace = bounds.top <= navHeight() + 1 && bounds.bottom > navHeight();
    const anchorIndex = enhanced ? Math.max(0, active) : Math.max(0, panels.findIndex(panel => {
      const rect = panel.getBoundingClientRect();
      return rect.bottom > navHeight() + 80;
    }));
    enhanced = next;
    story.dataset.enhanced = String(enhanced);
    active = -1;
    if (enhanced) {
      if (keepPlace) goTo(anchorIndex, false);
      update();
    }
    else {
      cancelAnimationFrame(pending);
      pending = 0;
      panels.forEach(panel => { panel.inert = false; panel.removeAttribute("aria-hidden"); });
      links.forEach(link => link.removeAttribute("aria-current"));
      if (keepPlace) panels[anchorIndex].scrollIntoView({ block: "center", behavior: "instant" });
    }
  }
  function goTo(index, smooth) {
    if (!enhanced) return;
    const top = window.scrollY + story.getBoundingClientRect().top - navHeight();
    const distance = Math.max(1, story.offsetHeight - frame.offsetHeight);
    const target = index === 0 ? 0 : (index + .5) / panels.length;
    window.scrollTo({ top: top + distance * target, behavior: smooth ? "smooth" : "instant" });
  }
  function followChapter(event) {
    if (!enhanced || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    const link = event.target.closest('a[href^="#"]');
    const index = panels.findIndex(panel => "#" + panel.id === link?.getAttribute("href"));
    if (index < 0) return;
    event.preventDefault();
    history.pushState(null, "", "#" + panels[index].id);
    goTo(index, true);
  }
  function followHash() {
    const index = panels.findIndex(panel => "#" + panel.id === location.hash);
    if (index >= 0) goTo(index, false);
  }
  function visibility() {
    if (document.visibilityState === "hidden") { cancelAnimationFrame(pending); pending = 0; }
    else schedule();
  }
  const intersection = "IntersectionObserver" in window ? new IntersectionObserver(entries => {
    inView = entries.some(entry => entry.isIntersecting);
    schedule();
  }, { rootMargin: "100px" }) : null;
  if (intersection) intersection.observe(story);
  else inView = true;
  const preference = new MutationObserver(setMode);
  preference.observe(root, { attributes: true, attributeFilter: ["data-cm-motion"] });
  desktop.addEventListener("change", setMode);
  reduced.addEventListener("change", setMode);
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule);
  window.addEventListener("hashchange", followHash);
  document.addEventListener("click", followChapter);
  document.addEventListener("visibilitychange", visibility);
  function resume() { setMode(); schedule(); }
  function cleanup(event) {
    if (event.persisted) { cancelAnimationFrame(pending); pending = 0; return; }
    intersection?.disconnect();
    preference.disconnect();
    desktop.removeEventListener("change", setMode);
    reduced.removeEventListener("change", setMode);
    window.removeEventListener("scroll", schedule);
    window.removeEventListener("resize", schedule);
    window.removeEventListener("hashchange", followHash);
    window.removeEventListener("pageshow", resume);
    window.removeEventListener("pagehide", cleanup);
    document.removeEventListener("click", followChapter);
    document.removeEventListener("visibilitychange", visibility);
    cancelAnimationFrame(pending);
  }
  window.addEventListener("pageshow", resume);
  window.addEventListener("pagehide", cleanup);
  setMode();
  followHash();
})();
