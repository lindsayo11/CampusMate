/* Lightweight vector orbit: no renderer, texture downloads, or per-frame JS. */
(() => {
  "use strict";
  const scene = document.querySelector(".stellar-scene");
  const orbit = scene?.querySelector(".stellar-orbit");
  if (!scene || !orbit || typeof orbit.animate !== "function") return;

  const root = document.documentElement;
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  const pointer = window.matchMedia("(hover: hover) and (pointer: fine)");
  const style = getComputedStyle(scene);
  const tokens = {
    orbit: Number(style.getPropertyValue("--stellar-orbit-seconds")) * 1000,
    twinkle: Number(style.getPropertyValue("--stellar-twinkle-seconds")) * 1000,
    samples: 180,
  };
  if (!(tokens.orbit > 0 && tokens.twinkle > 0)) return;

  // The visible ellipse is the source of truth for every orbit position.
  const cx = Number(orbit.getAttribute("cx"));
  const cy = Number(orbit.getAttribute("cy"));
  const rx = Number(orbit.getAttribute("rx"));
  const ry = Number(orbit.getAttribute("ry"));
  const tilt = Number(orbit.dataset.tilt) * Math.PI / 180;
  const cosTilt = Math.cos(tilt);
  const sinTilt = Math.sin(tilt);
  const animations = [];
  let inView = false;
  let hovered = false;

  function animate(element, keyframes, duration, delay = 0) {
    const animation = element.animate(keyframes, {
      duration, delay, iterations: Infinity, easing: "linear", fill: "both",
    });
    animation.pause();
    animation.currentTime = 0;
    animations.push(animation);
  }

  scene.querySelectorAll(".stellar-satellite").forEach(satellite => {
    const phase = Number(satellite.dataset.phase) * Math.PI / 180;
    const keyframes = Array.from({ length: tokens.samples + 1 }, (_, index) => {
      const angle = phase + index / tokens.samples * Math.PI * 2;
      const x = cx + rx * Math.cos(angle) * cosTilt - ry * Math.sin(angle) * sinTilt;
      const y = cy + rx * Math.cos(angle) * sinTilt + ry * Math.sin(angle) * cosTilt;
      // Translate the complete star + label together; never rotate the type.
      return { transform: `translate(${x.toFixed(4)}px, ${y.toFixed(4)}px)` };
    });
    animate(satellite, keyframes, tokens.orbit);
  });
  scene.querySelectorAll("[data-stellar-twinkle]").forEach((cluster, index) => {
    animate(cluster, [{ opacity: .4 }, { opacity: 1 }, { opacity: .4 }],
      tokens.twinkle, -index * tokens.twinkle / 4);
  });
  scene.querySelectorAll(".stellar-spark").forEach((spark, index) => {
    animate(spark, [{ opacity: .7 }, { opacity: 1 }, { opacity: .7 }],
      tokens.twinkle, -index * tokens.twinkle / 3);
  });

  function sync() {
    const running = root.dataset.cmMotion === "on" && !media.matches &&
      document.visibilityState === "visible" && inView && !hovered;
    animations.forEach(animation => {
      if (running && animation.playState !== "running") animation.play();
      if (!running && animation.playState !== "paused") animation.pause();
    });
    scene.dataset.orbitState = running ? "running" : "paused";
  }
  function enter() { hovered = pointer.matches; sync(); }
  function leave() { hovered = false; sync(); }

  const intersection = "IntersectionObserver" in window ? new IntersectionObserver(entries => {
    inView = entries.some(entry => entry.isIntersecting);
    sync();
  }) : null;
  if (intersection) intersection.observe(scene);
  else inView = true;
  const preference = new MutationObserver(sync);
  preference.observe(root, { attributes: true, attributeFilter: ["data-cm-motion"] });
  document.addEventListener("visibilitychange", sync);
  media.addEventListener("change", sync);
  scene.addEventListener("pointerenter", enter);
  scene.addEventListener("pointerleave", leave);
  function pagehide(event) {
    if (event.persisted) {
      animations.forEach(animation => animation.pause());
      return;
    }
    intersection?.disconnect();
    preference.disconnect();
    document.removeEventListener("visibilitychange", sync);
    media.removeEventListener("change", sync);
    scene.removeEventListener("pointerenter", enter);
    scene.removeEventListener("pointerleave", leave);
    window.removeEventListener("pageshow", sync);
    window.removeEventListener("pagehide", pagehide);
    animations.forEach(animation => animation.cancel());
  }
  window.addEventListener("pagehide", pagehide);
  window.addEventListener("pageshow", sync);
  sync();
})();
