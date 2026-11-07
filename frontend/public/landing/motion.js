/* No third-party requests: progressive motion for the four static public pages. */
(() => {
  "use strict";
  const tokens = { fast: 180, normal: 350, slow: 600, stagger: 70, distance: 24, ease: "cubic-bezier(.22,1,.36,1)" };
  const preferenceKey = "campusmate-motion";
  const root = document.documentElement;
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  const lowEnd = !!navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4;
  const animations = new Set();
  let enabled = false;
  let observer;
  let progressFrame = 0;
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "cm-motion-toggle";
  toggle.setAttribute("aria-label", "页面动效");
  const symbol = document.createElement("span");
  symbol.className = "cm-motion-symbol";
  symbol.setAttribute("aria-hidden", "true");
  const label = document.createElement("span");
  toggle.append(symbol, label);
  document.body.append(toggle);
  const progress = document.createElement("div");
  progress.className = "cm-reading-progress";
  progress.setAttribute("aria-hidden", "true");
  document.body.append(progress);

  // Enhance just the two homepage strips; keep one semantic, keyboard-accessible
  // set of items. Copies include the original SVG images, not nth-child icons.
  const marqueeCleanups = [];
  document.querySelectorAll("[data-marquee]").forEach(viewport => {
    const track = viewport.querySelector(".cm-marquee-track");
    if (!track || !track.children.length) return;
    const group = document.createElement("div");
    group.className = "cm-marquee-group";
    group.append(...track.children);
    track.append(group);
    let copyCount = 0;
    let resizeFrame = 0;
    let focusFrame = 0;

    function measure() {
      resizeFrame = 0;
      const distance = group.getBoundingClientRect().width;
      if (!distance) return;
      // Include the trailing gap in the distance so the loop cannot jump.
      track.style.setProperty("--cm-marquee-shift", `-${distance}px`);
      const required = Math.max(1, Math.ceil(viewport.clientWidth / distance));
      if (required !== copyCount) {
        track.querySelectorAll("[data-marquee-copy]").forEach(copy => copy.remove());
        for (let i = 0; i < required; i += 1) {
          const copy = group.cloneNode(true);
          copy.dataset.marqueeCopy = "true";
          copy.setAttribute("aria-hidden", "true");
          copy.querySelectorAll("a, button, [tabindex]").forEach(item => item.setAttribute("tabindex", "-1"));
          track.append(copy);
        }
        copyCount = required;
      }
      viewport.dataset.marqueeReady = "true";
    }
    function scheduleMeasure() {
      if (!resizeFrame) resizeFrame = requestAnimationFrame(measure);
    }
    function focusItem(event) {
      // Keyboard navigation switches to a stationary, scrollable list. A mouse
      // click only pauses the loop, so the link does not move under the pointer.
      if (!event.target.matches(":focus-visible")) return;
      cancelAnimationFrame(focusFrame);
      focusFrame = requestAnimationFrame(() => {
        if (event.target !== viewport) event.target.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
      });
    }
    function leaveFocus() {
      cancelAnimationFrame(focusFrame);
      focusFrame = requestAnimationFrame(() => {
        if (!viewport.contains(document.activeElement)) viewport.scrollLeft = 0;
      });
    }
    const resizeObserver = "ResizeObserver" in window ? new ResizeObserver(scheduleMeasure) : null;
    resizeObserver?.observe(viewport);
    resizeObserver?.observe(group);
    if (!resizeObserver) window.addEventListener("resize", scheduleMeasure);
    const loopObserver = "IntersectionObserver" in window ? new IntersectionObserver(entries => {
      entries.forEach(entry => viewport.style.setProperty("--cm-marquee-state", entry.isIntersecting ? "running" : "paused"));
    }) : null;
    loopObserver?.observe(viewport);
    if (!loopObserver) viewport.style.setProperty("--cm-marquee-state", "running");
    viewport.addEventListener("focusin", focusItem);
    viewport.addEventListener("focusout", leaveFocus);
    measure();
    marqueeCleanups.push(() => {
      resizeObserver?.disconnect();
      loopObserver?.disconnect();
      window.removeEventListener("resize", scheduleMeasure);
      viewport.removeEventListener("focusin", focusItem);
      viewport.removeEventListener("focusout", leaveFocus);
      cancelAnimationFrame(resizeFrame);
      cancelAnimationFrame(focusFrame);
    });
  });
  window.addEventListener("pagehide", event => {
    if (!event.persisted) marqueeCleanups.forEach(cleanup => cleanup());
  });

  function play(element, frames, delay = 0) {
    if (!enabled || !element.animate) return;
    const animation = element.animate(frames, { duration: tokens.slow, delay, easing: tokens.ease, fill: "backwards" });
    animations.add(animation);
    animation.finished.then(() => animations.delete(animation)).catch(() => animations.delete(animation));
  }
  function reveal() {
    observer?.disconnect();
    if (!enabled || !("IntersectionObserver" in window)) return;
    const targets = document.querySelectorAll(".hero-copy > *, .hero-visual, .section-copy, .source-art, .about-section > *, .security > *, .directory > *, .page-shell > :not(.source-layout), .source-layout > *, .ways-heading > *, .ways-page .way, .about-page > .about-brand, .about-columns > section");
    observer = new IntersectionObserver(entries => {
      entries.filter(entry => entry.isIntersecting).forEach((entry, index) => {
        observer.unobserve(entry.target);
        play(entry.target, [
          { opacity: .25, transform: `translateY(${tokens.distance}px)` },
          { opacity: 1, transform: "none" },
        ], Math.min(index, 5) * tokens.stagger);
        if (entry.target.classList.contains("hero-visual")) {
          entry.target.querySelectorAll(".orbit-card").forEach((card, i) => {
            play(card, [{ opacity: 0, transform: "translateY(16px)" }, { opacity: 1, transform: "none" }], tokens.normal + i * tokens.fast);
          });
        }
      });
    }, { threshold: .12 });
    targets.forEach(element => observer.observe(element));
  }
  function syncPreference() {
    let disabled = false;
    try { disabled = localStorage.getItem(preferenceKey) === "off"; } catch { /* Storage is optional. */ }
    enabled = !disabled && !media.matches && !lowEnd;
    root.dataset.cmMotion = enabled ? "on" : "off";
    toggle.setAttribute("aria-pressed", String(enabled));
    toggle.disabled = media.matches || lowEnd;
    toggle.title = toggle.disabled ? "已按系统设置或设备性能减少动效" : enabled ? "关闭页面动效" : "开启页面动效";
    symbol.textContent = enabled ? "Ⅱ" : "▷";
    label.textContent = enabled ? "动效开" : "动效关";
    animations.forEach(animation => animation.cancel());
    animations.clear();
    reveal();
  }
  toggle.addEventListener("click", () => {
    try { localStorage.setItem(preferenceKey, enabled ? "off" : "on"); } catch {
      enabled = !enabled;
      root.dataset.cmMotion = enabled ? "on" : "off";
      label.textContent = enabled ? "动效开" : "动效关";
      toggle.setAttribute("aria-pressed", String(enabled));
      if (!enabled) { animations.forEach(animation => animation.cancel()); observer?.disconnect(); }
      return;
    }
    syncPreference();
  });
  media.addEventListener("change", syncPreference);
  window.addEventListener("storage", event => { if (event.key === preferenceKey) syncPreference(); });
  function visibility() {
    const hidden = document.visibilityState === "hidden";
    root.dataset.cmHidden = String(hidden);
    animations.forEach(animation => hidden ? animation.pause() : animation.play());
  }
  document.addEventListener("visibilitychange", visibility);
  const sections = [...document.querySelectorAll("main > section[id]")];
  function updateProgress() {
    const max = root.scrollHeight - window.innerHeight;
    progress.style.transform = `scaleX(${max > 0 ? Math.min(1,Math.max(0,window.scrollY / max)) : 0})`;
    const current = sections.filter(section => section.getBoundingClientRect().top < window.innerHeight * .4).at(-1);
    document.querySelectorAll(".nav-trigger[href^='#']").forEach(link => {
      if (current && link.hash === "#" + current.id) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
    progressFrame = 0;
  }
  function scheduleProgress() { if (!progressFrame) progressFrame = requestAnimationFrame(updateProgress); }
  window.addEventListener("scroll", scheduleProgress, { passive: true });
  window.addEventListener("resize", scheduleProgress);
  const hero = document.querySelector(".hero-visual");
  if (hero && window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
    hero.addEventListener("pointermove", event => {
      if (!enabled) return;
      const rect = hero.getBoundingClientRect();
      hero.style.setProperty("--orbit-x", `${((event.clientX - rect.left) / rect.width - .5) * tokens.distance}px`);
      hero.style.setProperty("--orbit-y", `${((event.clientY - rect.top) / rect.height - .5) * tokens.distance}px`);
    });
    hero.addEventListener("pointerleave", () => {
      hero.style.setProperty("--orbit-x", "0px");
      hero.style.setProperty("--orbit-y", "0px");
    });
  }
  syncPreference();
  visibility();
  updateProgress();
})();
