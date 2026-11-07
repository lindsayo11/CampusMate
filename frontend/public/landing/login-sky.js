/* Local decoration only. No authentication hooks, requests or animation loop. */
(() => {
  "use strict";
  const sky = document.querySelector(".login-sky");
  if (!sky) return;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const fragment = document.createDocumentFragment();
  let seed = 731;
  const random = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
  for (let i = 0; i < 88; i++) {
    const star = document.createElement("span");
    star.className = "night-star" + (i % 7 === 0 ? " is-bright" : "");
    star.style.left = (2 + random() * 96).toFixed(2) + "%";
    star.style.top = (2 + random() * 96).toFixed(2) + "%";
    star.style.setProperty("--star-size", (i % 7 === 0 ? 1.8 : .8 + random() * .65).toFixed(2) + "px");
    star.style.setProperty("--star-opacity", (.25 + random() * .55).toFixed(2));
    star.style.setProperty("--star-delay", (-random() * 6).toFixed(2) + "s");
    fragment.append(star);
  }
  const meteors = [
    { x: 53, y: 10, travel: 460, trail: 170, cycle: 8.6, delay: .6 },
    { x: 7, y: 5, travel: 430, trail: 145, cycle: 10.4, delay: 2.8 },
    { x: 20, y: 68, travel: 360, trail: 125, cycle: 13.2, delay: 5.2 },
    { x: 75, y: 24, travel: 320, trail: 135, cycle: 11.8, delay: 7.5 },
    { x: 34, y: 18, travel: 410, trail: 155, cycle: 15.1, delay: 10.1 },
  ];
  meteors.forEach(({ x, y, travel, trail, cycle, delay }) => {
    const meteor = document.createElement("span");
    meteor.className = "night-meteor";
    meteor.style.left = x + "%";
    meteor.style.top = y + "%";
    Object.entries({ "--travel-x": travel + "px", "--travel-y": (travel * Math.tan(32 * Math.PI / 180)).toFixed(1) + "px", "--trail": trail + "px", "--cycle": cycle + "s", "--delay": delay + "s" }).forEach(([name, value]) => meteor.style.setProperty(name, value));
    fragment.append(meteor);
  });
  sky.append(fragment);
  function sync() {
    let disabled = false;
    try { disabled = localStorage.getItem("campusmate-motion") === "off"; } catch { /* Optional preference. */ }
    sky.dataset.skyMotion = reduced.matches || disabled ? "off" : "on";
    sky.dataset.skyPaused = String(document.visibilityState === "hidden");
  }
  const storage = event => { if (event.key === "campusmate-motion" || event.key === null) sync(); };
  function cleanup(event) {
    if (event.persisted) { sky.dataset.skyPaused = "true"; return; }
    reduced.removeEventListener("change", sync);
    document.removeEventListener("visibilitychange", sync);
    window.removeEventListener("storage", storage);
    window.removeEventListener("pageshow", sync);
    window.removeEventListener("pagehide", cleanup);
  }
  reduced.addEventListener("change", sync);
  document.addEventListener("visibilitychange", sync);
  window.addEventListener("storage", storage);
  window.addEventListener("pageshow", sync);
  window.addEventListener("pagehide", cleanup);
  sync();
})();
