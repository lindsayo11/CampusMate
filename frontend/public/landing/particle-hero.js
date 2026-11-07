/* A finite local canvas sequence. No network, shared motion changes, or scroll lock. */
(() => {
  "use strict";
  const hero = document.querySelector(".particle-hero");
  if (!hero) return;
  const root = document.documentElement;
  const canvas = hero.querySelector(".particle-canvas");
  const copy = hero.querySelector(".particle-copy");
  const parts = [...copy.children];
  const actions = hero.querySelector(".actions");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const style = getComputedStyle(hero);
  const token = name => Number(style.getPropertyValue("--particle-" + name));
  const timing = {
    grid: token("grid-time"), gather: token("gather-time"), round: token("round-time"), point: token("point-time"),
    burst: token("burst-time"), title: token("title-time"), copy: token("copy-time"),
    action: token("action-time"), gap: token("reveal-gap"), rise: token("rise"),
  };
  const pointStart = timing.grid + timing.gather;
  const burstStart = pointStart + timing.point;
  const titleStart = burstStart + timing.burst;
  const copyStart = titleStart + timing.title + timing.gap;
  const actionStart = copyStart + timing.copy + timing.gap;
  const total = actionStart + timing.action;
  const clamp = value => Math.min(1, Math.max(0, value));
  const smooth = value => value * value * (3 - 2 * value);
  const easeOut = value => 1 - Math.pow(1 - value, 3);
  let context;
  try { context = canvas.getContext("2d", { alpha: false }); } catch { /* Text is the fallback. */ }
  let width = 0, height = 0, points = [];
  let frame = 0, elapsed = 0, previous = 0, running = false, paused = false;
  let phase = "", inView = true, disposed = false;
  const pointer = { x: 0, y: 0, targetX: 0, targetY: 0, strength: 0, active: false };

  function allowed() {
    return !!context && !reduced.matches && root.dataset.cmMotion === "on" &&
      !(navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4);
  }
  function setPhase(next) {
    if (phase === next) return;
    phase = next;
    hero.dataset.heroPhase = next;
  }
  function measure() {
    width = hero.clientWidth;
    height = hero.clientHeight;
    const scale = Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(5000000 / Math.max(1, width * height)));
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    context.setTransform(scale, 0, 0, scale, 0, 0);
    const spacing = Math.max(width < 600 ? 27 : 34, Math.sqrt(width * height / 1600));
    const columns = Math.max(1, Math.floor(width / spacing));
    const rows = Math.max(1, Math.floor(height / spacing));
    const offsetX = (width - (columns - 1) * spacing) / 2;
    const offsetY = (height - (rows - 1) * spacing) / 2;
    points = [];
    for (let row = 0; row < rows; row++) {
      for (let column = 0; column < columns; column++) {
        const index = row * columns + column;
        const seed = Math.sin((index + 1) * 12.9898) * 43758.5453;
        const random = seed - Math.floor(seed);
        const driftSeed = Math.sin((index + 1) * 78.233) * 19341.237;
        const drift = driftSeed - Math.floor(driftSeed);
        const angle = index * 2.399963229728653;
        const dx = Math.cos(angle), dy = Math.sin(angle);
        const x = offsetX + column * spacing, y = offsetY + row * spacing;
        const nx = (x - width / 2) / (width / 2);
        const ny = (y - height / 2) / (height / 2);
        const diskRadius = Math.min(width, height) * .46;
        points.push({
          x, y,
          ox: 0, oy: 0, shade: (row + column) % 2 ? .54 : .88,
          // Map the rectangular grid to a disk before it reaches the core.
          // Each particle has a different arrival time and curved inward path.
          diskX: nx * Math.sqrt(1 - ny * ny / 2) * diskRadius,
          diskY: ny * Math.sqrt(1 - nx * nx / 2) * diskRadius,
          delay: random * .1, duration: .74 + drift * .16,
          bend: (drift - .5) * .7, previousX: null, previousY: null,
          random, dx, dy, flight: Math.hypot(width, height) * (.65 + random * .95) + 80,
        });
      }
    }
  }
  function dot(x, y, radius, opacity) {
    context.globalAlpha = clamp(opacity);
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.fill();
  }
  function pointGlow(radius, opacity) {
    const gradient = context.createRadialGradient(width / 2, height / 2, 0, width / 2, height / 2, radius);
    gradient.addColorStop(0, "rgba(255,255,255,.6)");
    gradient.addColorStop(.2, "rgba(255,255,255,.15)");
    gradient.addColorStop(1, "rgba(255,255,255,0)");
    context.globalAlpha = opacity;
    context.fillStyle = gradient;
    context.fillRect(width / 2 - radius, height / 2 - radius, radius * 2, radius * 2);
    context.fillStyle = "#fff";
  }
  function draw(time, delta) {
    context.globalAlpha = 1;
    context.fillStyle = "#000";
    context.fillRect(0, 0, width, height);
    context.fillStyle = "#fff";
    const centerX = width / 2, centerY = height / 2;
    if (time < timing.grid) {
      setPhase("grid");
      const follow = 1 - Math.exp(-delta / 85);
      pointer.x += (pointer.targetX - pointer.x) * follow;
      pointer.y += (pointer.targetY - pointer.y) * follow;
      pointer.strength += ((pointer.active ? 1 : 0) - pointer.strength) * follow;
      const radius = Math.min(190, width * .38);
      for (const p of points) {
        const dx = p.x - pointer.x, dy = p.y - pointer.y;
        const distance = Math.hypot(dx, dy);
        const influence = Math.pow(clamp(1 - distance / radius), 2) * pointer.strength;
        const force = influence * 58;
        p.ox = dx / Math.max(1, distance) * force;
        p.oy = dy / Math.max(1, distance) * force;
        dot(p.x + p.ox, p.y + p.oy, 1.35 + influence * .8, p.shade + influence * .35);
      }
    } else if (time < pointStart) {
      setPhase("gather");
      const gatheringTime = time - timing.grid;
      const progress = gatheringTime / timing.gather;
      // Finish forming the circle at full size BEFORE reducing its radius.
      // Scaling during this transition would preserve a miniature rectangle.
      const circularize = easeOut(clamp(gatheringTime / timing.round));
      const inwardProgress = clamp((gatheringTime - timing.round) / (timing.gather - timing.round));
      for (const p of points) {
        const local = clamp((inwardProgress - p.delay) / p.duration);
        const remaining = Math.pow(1 - smooth(local), 1.15);
        const angle = Math.sin(local * Math.PI) * p.bend;
        const dx = p.x + p.ox - centerX, dy = p.y + p.oy - centerY;
        const inwardX = dx + (p.diskX - dx) * circularize;
        const inwardY = dy + (p.diskY - dy) * circularize;
        const x = centerX + (inwardX * Math.cos(angle) - inwardY * Math.sin(angle)) * remaining;
        const y = centerY + (inwardX * Math.sin(angle) + inwardY * Math.cos(angle)) * remaining;
        if (p.previousX !== null && progress > .12 && progress < .88) {
          context.globalAlpha = p.shade * .2;
          context.strokeStyle = "#fff";
          context.lineWidth = .7;
          context.beginPath();
          context.moveTo(p.previousX, p.previousY);
          context.lineTo(x, y);
          context.stroke();
        }
        p.previousX = x; p.previousY = y;
        dot(x, y, 1.35 - local * .6, p.shade);
      }
      if (progress > .65) pointGlow(34, (progress - .65) / .35);
    } else if (time < burstStart) {
      setPhase("point");
      pointGlow(36, 1);
      dot(centerX, centerY, 3.2, 1);
    } else if (time < titleStart) {
      setPhase("burst");
      const progress = clamp((time - burstStart) / timing.burst);
      for (const p of points) {
        const local = clamp((progress - p.random * .045) / (1 - p.random * .045));
        const travel = Math.pow(local, 1.65) * p.flight;
        const trail = Math.pow(Math.max(0, local - .045), 1.65) * p.flight;
        const x = centerX + p.dx * travel, y = centerY + p.dy * travel;
        if (x < -30 || x > width + 30 || y < -30 || y > height + 30) continue;
        const alpha = (1 - smooth(clamp((local - .8) / .2))) * p.shade;
        context.globalAlpha = alpha * .3;
        context.strokeStyle = "#fff";
        context.lineWidth = .65 + local * 1.1;
        context.beginPath();
        context.moveTo(centerX + p.dx * trail, centerY + p.dy * trail);
        context.lineTo(x, y);
        context.stroke();
        dot(x, y, 1 + local * (2 + p.random * 2), alpha);
      }
      if (progress < .12) pointGlow(36, 1 - progress / .12);
    }
  }
  function reveal(element, time, start, duration) {
    const progress = easeOut(clamp((time - start) / duration));
    element.style.opacity = String(progress);
    element.style.transform = "translate3d(0," + ((1 - progress) * timing.rise) + "px,0)";
  }
  function finish(reason = "complete") {
    running = false;
    cancelAnimationFrame(frame);
    frame = 0;
    canvas.hidden = true;
    hero.dataset.heroState = "complete";
    hero.dataset.heroFinish = reason;
    setPhase("complete");
    parts.forEach(part => { part.style.removeProperty("opacity"); part.style.removeProperty("transform"); });
    actions.inert = false;
  }
  function tick(now) {
    frame = 0;
    if (!running || paused || disposed) return;
    const delta = previous ? Math.min(64, Math.max(0, now - previous)) : 0;
    previous = now;
    elapsed += delta;
    try {
      if (elapsed < titleStart) draw(elapsed, delta);
      else {
        canvas.hidden = true;
        setPhase(elapsed < copyStart ? "title" : elapsed < actionStart ? "description" : "actions");
      }
      reveal(parts[0], elapsed, titleStart, timing.title);
      reveal(parts[1], elapsed, copyStart, timing.copy);
      reveal(parts[2], elapsed, actionStart, timing.action);
      if (elapsed >= actionStart) actions.inert = false;
      if (elapsed >= total) finish();
      else frame = requestAnimationFrame(tick);
    } catch { finish("canvas-unavailable"); }
  }
  function start() {
    if (disposed || !allowed()) { finish("motion-disabled"); return; }
    if (running) cancelAnimationFrame(frame);
    try { measure(); } catch { finish("canvas-unavailable"); return; }
    elapsed = 0; previous = 0; running = true; paused = document.visibilityState === "hidden";
    pointer.active = false; pointer.strength = 0;
    canvas.hidden = false;
    hero.dataset.heroState = "playing";
    delete hero.dataset.heroFinish;
    actions.inert = true;
    try { draw(0, 0); } catch { finish("canvas-unavailable"); return; }
    parts.forEach(part => { part.style.opacity = "0"; part.style.transform = "translate3d(0," + timing.rise + "px,0)"; });
    if (!paused) frame = requestAnimationFrame(tick);
  }
  function move(event) {
    if (!running || phase !== "grid") return;
    const rect = hero.getBoundingClientRect();
    pointer.targetX = event.clientX - rect.left;
    pointer.targetY = event.clientY - rect.top;
    if (!pointer.active) { pointer.x = pointer.targetX; pointer.y = pointer.targetY; }
    pointer.active = true;
  }
  function leave() { pointer.active = false; }
  function release(event) { if (event.pointerType !== "mouse") leave(); }
  function key(event) {
    if (running && (event.key === "Escape" || event.key === "Tab")) finish("keyboard-skip");
  }
  function preferenceChanged() {
    if (!allowed()) finish("motion-disabled");
  }
  function visibility() {
    paused = document.visibilityState === "hidden";
    previous = 0;
    cancelAnimationFrame(frame);
    frame = 0;
    if (running && !paused && inView) frame = requestAnimationFrame(tick);
  }
  function resize() {
    if (!running) return;
    try { measure(); } catch { finish("canvas-unavailable"); }
  }
  function fallbackScroll() {
    if (running && hero.getBoundingClientRect().bottom <= 72) finish("offscreen");
  }
  const observer = "IntersectionObserver" in window ? new IntersectionObserver(entries => {
    inView = entries[0].isIntersecting;
    if (!inView && running) finish("offscreen");
  }) : null;
  const preference = new MutationObserver(preferenceChanged);
  preference.observe(root, { attributes: true, attributeFilter: ["data-cm-motion"] });
  observer?.observe(hero);
  if (!observer) window.addEventListener("scroll", fallbackScroll, { passive: true });
  hero.addEventListener("pointermove", move, { passive: true });
  hero.addEventListener("pointerleave", leave);
  hero.addEventListener("pointerup", release, { passive: true });
  document.addEventListener("keydown", key);
  document.addEventListener("visibilitychange", visibility);
  window.addEventListener("resize", resize);
  reduced.addEventListener("change", preferenceChanged);
  function enter() {
    // A fresh homepage visit/reload always starts at the opening, not a restored
    // scroll position. In-page navigation remains available during the sequence.
    try {
      history.scrollRestoration = "manual";
      if (location.hash && location.hash !== "#top") history.replaceState(history.state, "", location.pathname + location.search + "#top");
    } catch { /* The intro also works when history APIs are unavailable. */ }
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    inView = true;
    start();
  }
  function resume(event) {
    if (!allowed()) finish("motion-disabled");
    else if (event.persisted) enter();
    else visibility();
  }
  function cleanup(event) {
    cancelAnimationFrame(frame);
    frame = 0;
    if (event.persisted) { paused = true; previous = 0; return; }
    disposed = true;
    observer?.disconnect(); preference.disconnect();
    hero.removeEventListener("pointermove", move);
    hero.removeEventListener("pointerleave", leave);
    hero.removeEventListener("pointerup", release);
    document.removeEventListener("keydown", key);
    document.removeEventListener("visibilitychange", visibility);
    window.removeEventListener("resize", resize);
    window.removeEventListener("scroll", fallbackScroll);
    reduced.removeEventListener("change", preferenceChanged);
    window.removeEventListener("pageshow", resume);
    window.removeEventListener("pagehide", cleanup);
  }
  window.addEventListener("pageshow", resume);
  window.addEventListener("pagehide", cleanup);
  if (!Object.values(timing).every(Number.isFinite) || total <= 0 || !allowed()) finish("motion-disabled");
  else enter();
})();
