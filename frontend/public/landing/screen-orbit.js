/* A PC gallery of genuine local page captures; no account/API writes. */
(() => {
  "use strict";
  const gallery = document.querySelector(".screen-orbit");
  if (!gallery) return;
  const stage = gallery.querySelector(".orbit-stage");
  const scene = gallery.querySelector(".orbit-frame");
  const content = gallery.querySelector(".orbit-content");
  const nextScene = document.querySelector("#journey");
  const cards = [...gallery.querySelectorAll("[data-orbit-card]")];
  const choices = [...gallery.querySelectorAll("[data-orbit-select]")];
  if (!cards.length) return;
  const inspect = gallery.querySelector("[data-orbit-inspect]");
  const caption = gallery.querySelector("[data-orbit-caption]");
  const status = gallery.querySelector("[data-orbit-status]");
  const dialog = gallery.querySelector(".orbit-dialog");
  const close = gallery.querySelector("[data-orbit-close]");
  const fullImage = gallery.querySelector("[data-orbit-full-image]");
  const fullError = gallery.querySelector("[data-orbit-full-error]");
  const openLink = gallery.querySelector("[data-orbit-open]");
  const title = gallery.querySelector("#orbit-dialog-title");
  const root = document.documentElement;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const desktop = window.matchMedia("(min-width: 1000px)");
  const styles = getComputedStyle(gallery);
  const cycle = Number(styles.getPropertyValue("--orbit-cycle")) || 40;
  const approach = Number(styles.getPropertyValue("--orbit-approach")) || 10;
  const dragScale = Number(styles.getPropertyValue("--orbit-drag-scale")) || .006;
  const scrollTurns = Number(styles.getPropertyValue("--orbit-scroll-turns")) || 2;
  const blurMax = Number(styles.getPropertyValue("--orbit-blur-max")) || 18;
  const handoffDelay = Number(styles.getPropertyValue("--orbit-handoff-delay")) || 180;
  const step = Math.PI * 2 / cards.length;
  let rotation = 0, target = null, selected = -1, frame = 0, last = 0;
  let radiusX = 0, radiusY = 0, inView = false, focused = false;
  let enhanced = false, pointer = null, blockClickUntil = 0, opener = null;
  let scrollEnabled = false, scrollRotation = 0, scrollFrame = 0;
  let handoffTimer = 0, handoffSent = false, forwardUntil = 0, advancing = false;
  const removals = [];
  const on = (node, event, callback, options) => {
    node.addEventListener(event, callback, options);
    removals.push(() => node.removeEventListener(event, callback, options));
  };
  const modulo = (value, base) => ((value % base) + base) % base;
  const clamp = value => Math.max(0, Math.min(1, value));
  const smooth = value => value * value * (3 - 2 * value);
  const nearest = () => modulo(Math.round(-(rotation + scrollRotation) / step), cards.length);
  const navHeight = () => document.querySelector("header.nav")?.offsetHeight || 72;
  const canMove = () => !reduced.matches && root.dataset.cmMotion === "on";
  function cancelHandoff() {
    clearTimeout(handoffTimer); handoffTimer = 0;
    if (advancing) window.scrollTo({ top: window.scrollY, behavior: "instant" });
    advancing = false;
  }
  function updateScroll() {
    scrollFrame = 0;
    if (!scrollEnabled) return;
    const bounds = gallery.getBoundingClientRect();
    const distance = Math.max(1, gallery.offsetHeight - scene.offsetHeight - 2);
    const progress = clamp((navHeight() - bounds.top) / distance);
    // Scroll distance adds exactly two turns; faster native scroll increases
    // angular velocity without swallowing wheel, trackpad or keyboard input.
    scrollRotation = progress * Math.PI * 2 * scrollTurns;
    const viewing = focused || dialog.open;
    const veilProgress = viewing ? 0 : progress;
    scene.style.setProperty("--orbit-veil", String(smooth(clamp(veilProgress / .96))));
    scene.style.setProperty("--orbit-blur", (Math.pow(veilProgress, 1.15) * blurMax).toFixed(2) + "px");
    gallery.dataset.orbitProgress = progress.toFixed(4);
    gallery.dataset.orbitPhase = progress >= 1 ? "covered" : progress > 0 ? "veiling" : "orbit";
    content.inert = progress >= .96 && !viewing;
    render();
    schedule();
    if (progress < .8) handoffSent = false;
    if (progress < 1 || bounds.bottom <= navHeight()) {
      clearTimeout(handoffTimer); handoffTimer = 0;
    }
    if (progress >= 1 && bounds.bottom > navHeight() && forwardUntil > performance.now() &&
        !handoffSent && !handoffTimer && !focused && !pointer && !dialog.open && nextScene) {
      handoffTimer = setTimeout(() => {
        handoffTimer = 0;
        if (!scrollEnabled || document.visibilityState === "hidden" || dialog.open || focused || pointer ||
            Number(gallery.dataset.orbitProgress) < 1 || gallery.getBoundingClientRect().bottom <= navHeight()) return;
        handoffSent = true;
        advancing = true;
        // One short native hand-off, only after deliberate downward scrolling.
        // Upward wheel, navigation or keyboard input can interrupt it at once.
        window.scrollTo({ top: window.scrollY + nextScene.getBoundingClientRect().top - navHeight(), behavior: "smooth" });
      }, handoffDelay);
    }
  }
  function scheduleScroll() {
    if (scrollEnabled && !scrollFrame && document.visibilityState !== "hidden") scrollFrame = requestAnimationFrame(updateScroll);
  }
  function active(index, announce = false) {
    if (index !== selected) {
      selected = index;
      choices.forEach((button, i) => button.setAttribute("aria-pressed", String(i === index)));
      caption.textContent = cards[index].dataset.caption;
      inspect.firstChild.textContent = "查看" + cards[index].dataset.title + " ";
    }
    if (announce) status.textContent = "当前展示：" + cards[index].dataset.title;
  }
  function render() {
    if (!enhanced) return;
    cards.forEach((card, index) => {
      const angle = rotation + scrollRotation + index * step;
      const depth = (Math.cos(angle) + 1) / 2;
      const x = Math.sin(angle) * radiusX;
      const y = Math.cos(angle) * radiusY;
      const scale = .6 + .4 * depth;
      card.style.transform = "translate(-50%,-50%) translate3d(" + x.toFixed(2) + "px," + y.toFixed(2) + "px,0) perspective(1200px) rotateY(" + (-Math.sin(angle) * 24).toFixed(2) + "deg) rotateZ(" + (Math.sin(angle) * 4).toFixed(2) + "deg) scale(" + scale.toFixed(3) + ")";
      card.style.opacity = String(.25 + .75 * depth);
      card.style.zIndex = String(depth > .6 ? 10 + Math.round(depth * 10) : 1 + Math.round(depth * 5));
    });
    if (target === null) active(nearest());
  }
  function measure() {
    radiusX = stage.clientWidth * .47;
    radiusY = stage.clientHeight * .365;
    if (scrollEnabled) radiusY = Math.min(radiusY, Math.max(0, (stage.clientHeight - Math.max(...cards.map(card => card.offsetHeight))) / 2 - 10));
    render();
    scheduleScroll();
  }
  function willRun() {
    return enhanced && inView && document.visibilityState !== "hidden" && !dialog.open && gallery.dataset.orbitPhase !== "covered" &&
      (target !== null || (!focused && !pointer));
  }
  function schedule() {
    if (!frame && willRun()) { last = 0; frame = requestAnimationFrame(tick); }
  }
  function tick(time) {
    frame = 0;
    if (!willRun()) return;
    const delta = last ? Math.min(.05, (time - last) / 1000) : 0;
    last = time;
    if (target !== null) {
      const difference = target - rotation;
      rotation += difference * (1 - Math.exp(-approach * delta));
      if (Math.abs(difference) < .001) { rotation = target; target = null; }
    } else rotation += delta * Math.PI * 2 / cycle;
    render();
    if (willRun()) frame = requestAnimationFrame(tick);
  }
  function select(index) {
    index = modulo(index, cards.length);
    if (!enhanced) { active(index, true); return; }
    const difference = modulo(-index * step - rotation - scrollRotation + Math.PI, Math.PI * 2) - Math.PI;
    target = rotation + difference;
    active(index, true);
    schedule();
  }
  function mode() {
    const before = gallery.getBoundingClientRect();
    const wasScroll = scrollEnabled;
    const keepPlace = wasScroll && before.top <= navHeight() && before.bottom > navHeight();
    enhanced = canMove();
    scrollEnabled = enhanced && desktop.matches && !!scene && !!content;
    gallery.dataset.orbitReady = String(enhanced);
    gallery.dataset.orbitScroll = String(scrollEnabled);
    gallery.querySelector("[data-orbit-hint]").textContent = enhanced ? "下滚加速 · 拖动旋转 · 点击截图放大" : "点击截图放大";
    if (!scrollEnabled) {
      cancelHandoff(); cancelAnimationFrame(scrollFrame); scrollFrame = 0;
      scrollRotation = 0; forwardUntil = 0; handoffSent = false;
      content.inert = false;
      scene.style.removeProperty("--orbit-veil"); scene.style.removeProperty("--orbit-blur");
      gallery.dataset.orbitProgress = "0"; gallery.dataset.orbitPhase = "static";
      if (keepPlace) window.scrollTo({ top: window.scrollY + gallery.getBoundingClientRect().top - navHeight(), behavior: "instant" });
    }
    if (!enhanced) {
      cancelAnimationFrame(frame); frame = 0; target = null;
      cards.forEach(card => { card.style.removeProperty("transform"); card.style.removeProperty("opacity"); card.style.removeProperty("z-index"); });
    } else { measure(); schedule(); }
  }
  function preview(index, source) {
    cancelHandoff(); forwardUntil = 0;
    const card = cards[index];
    opener = source || card;
    title.textContent = card.dataset.title;
    fullError.hidden = true;
    fullImage.hidden = false;
    fullImage.alt = card.querySelector("img").alt;
    fullImage.src = card.querySelector("img").getAttribute("src");
    openLink.href = card.getAttribute("href");
    openLink.firstChild.textContent = "进入" + card.dataset.title + " ";
    dialog.showModal();
    cancelAnimationFrame(frame); frame = 0;
  }
  on(stage, "pointerdown", event => {
    if (!enhanced || event.button !== 0 || event.target.closest(".orbit-center") || event.pointerType !== "mouse") return;
    pointer = { id: event.pointerId, start: event.clientX, rotation, moved: false };
    target = null;
  });
  on(stage, "pointermove", event => {
    if (!pointer || pointer.id !== event.pointerId) return;
    const distance = event.clientX - pointer.start;
    if (!pointer.moved && Math.abs(distance) < 7) return;
    pointer.moved = true;
    if (!stage.hasPointerCapture(event.pointerId)) stage.setPointerCapture(event.pointerId);
    stage.classList.add("is-dragging");
    rotation = pointer.rotation + distance * dragScale;
    render();
  });
  const release = event => {
    if (!pointer || event.pointerId !== pointer.id) return;
    if (pointer.moved) { blockClickUntil = performance.now() + 250; active(nearest(), true); }
    if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
    pointer = null; stage.classList.remove("is-dragging"); schedule();
  };
  on(stage, "pointerup", release);
  on(stage, "pointercancel", release);
  on(stage, "dragstart", event => event.preventDefault());
  on(gallery, "focusin", event => { focused = event.target.matches(":focus-visible"); scheduleScroll(); schedule(); });
  on(gallery, "focusout", event => { focused = !!event.relatedTarget && gallery.contains(event.relatedTarget) && event.relatedTarget.matches(":focus-visible"); scheduleScroll(); schedule(); });
  on(gallery, "keydown", () => { focused = true; scheduleScroll(); });
  on(gallery, "pointerdown", () => { focused = false; scheduleScroll(); schedule(); });
  on(stage, "keydown", event => {
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); select(selected + (event.key === "ArrowRight" ? 1 : -1)); }
  });
  cards.forEach((card, index) => {
    on(card, "focus", () => { if (card.matches(":focus-visible")) select(index); });
    on(card, "click", event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      if (performance.now() >= blockClickUntil) preview(index, card);
    });
    const img = card.querySelector("img");
    const error = () => { img.hidden = true; card.querySelector(".orbit-image-error").hidden = false; };
    on(img, "error", error);
    if (img.complete && !img.naturalWidth) error();
  });
  choices.forEach((button, index) => on(button, "click", () => select(index)));
  on(inspect, "click", () => preview(Math.max(0, selected), inspect));
  on(close, "click", () => dialog.close());
  on(dialog, "click", event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } });
  on(dialog, "close", () => { opener?.focus({ preventScroll: true }); schedule(); });
  on(fullImage, "error", () => { fullImage.hidden = true; fullError.hidden = false; });
  on(window, "scroll", scheduleScroll, { passive: true });
  on(window, "wheel", event => {
    if (event.ctrlKey || !scrollEnabled) return;
    if (event.deltaY < 0) { forwardUntil = 0; cancelHandoff(); }
    else if (event.deltaY > 0) {
      const bounds = gallery.getBoundingClientRect();
      if (bounds.top <= navHeight() + 1 && bounds.bottom > navHeight()) forwardUntil = performance.now() + 650;
    }
    scheduleScroll();
  }, { passive: true });
  on(window, "keydown", event => {
    if (["ArrowUp", "PageUp", "Home", "Tab", "Escape"].includes(event.key)) { forwardUntil = 0; cancelHandoff(); }
  });
  on(document, "click", event => { if (event.target.closest("header.nav a")) { forwardUntil = 0; cancelHandoff(); } });
  on(document, "visibilitychange", () => {
    cancelAnimationFrame(frame); frame = 0;
    if (document.visibilityState === "hidden") { clearTimeout(handoffTimer); handoffTimer = 0; cancelAnimationFrame(scrollFrame); scrollFrame = 0; }
    else scheduleScroll();
    schedule();
  });
  on(reduced, "change", mode);
  on(desktop, "change", mode);
  const preferences = new MutationObserver(mode);
  preferences.observe(root, { attributes: true, attributeFilter: ["data-cm-motion"] });
  const observer = new IntersectionObserver(entries => {
    inView = entries[0].isIntersecting;
    if (!inView) { cancelAnimationFrame(frame); frame = 0; } else schedule();
  }, { threshold: .05 });
  observer.observe(scene);
  const resize = new ResizeObserver(measure);
  resize.observe(stage);
  on(window, "pagehide", event => {
    cancelAnimationFrame(frame); frame = 0;
    cancelAnimationFrame(scrollFrame); scrollFrame = 0;
    clearTimeout(handoffTimer); handoffTimer = 0;
    if (event.persisted) return;
    observer.disconnect(); resize.disconnect(); preferences.disconnect();
    removals.forEach(remove => remove());
  });
  on(window, "pageshow", () => { scheduleScroll(); schedule(); });
  active(0);
  mode();
})();
