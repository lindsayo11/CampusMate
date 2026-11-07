"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { animate, AnimatePresence, motion, MotionConfig, useAnimate, useInView, useReducedMotion } from "motion/react";
import { motionPreferenceKey, motionTokens, shouldAnimate, springs } from "@/lib/motion-tokens";

const MotionContext = createContext({ enabled: false, limited: false, toggle: () => {} });

export function MotionPreferences({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  const [ready, setReady] = useState(false);
  const [disabled, setDisabled] = useState(false);
  const [limited, setLimited] = useState(false);
  useEffect(() => {
    const sync = () => {
      try { setDisabled(localStorage.getItem(motionPreferenceKey) === "off"); } catch { /* Storage is optional. */ }
      setLimited(!shouldAnimate({ essential: false }));
      setReady(true);
    };
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    sync();
    media.addEventListener("change", sync);
    window.addEventListener("storage", sync);
    return () => {
      media.removeEventListener("change", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  // useReducedMotion supplies the initial preference. Our media listener also
  // handles live system changes, without requiring a reload.
  const systemLimited = ready ? limited : !!reduced;
  const enabled = ready && !disabled && !systemLimited;
  useEffect(() => {
    document.documentElement.dataset.cmMotion = enabled ? "on" : "off";
    return () => { delete document.documentElement.dataset.cmMotion; };
  }, [enabled]);
  const toggle = () => {
    if (systemLimited) return;
    const next = !disabled;
    setDisabled(next);
    try { localStorage.setItem(motionPreferenceKey, next ? "off" : "on"); } catch { /* Keep the in-memory preference. */ }
  };
  return <MotionContext.Provider value={{ enabled, limited: systemLimited, toggle }}>
    <MotionConfig reducedMotion="user" transition={springs.snappy}>{children}</MotionConfig>
  </MotionContext.Provider>;
}

export function MotionToggle() {
  const { enabled, limited, toggle } = useContext(MotionContext);
  return <button type="button" className="motion-toggle" aria-label="页面动效" aria-pressed={enabled}
    disabled={limited} title={limited ? "已按系统设置或设备性能减少动效" : enabled ? "关闭页面动效" : "开启页面动效"} onClick={toggle}>
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
      {enabled ? <><path d="M9 5v14M15 5v14"/><path d="M4 9v6M20 9v6"/></> : <path d="m9 5 10 7-10 7Z"/>}
    </svg><span>动效{enabled ? "开" : "关"}</span>
  </button>;
}

/** Tiny shared marker; never layout-animate the sidebar or the entire page. */
export function NavMarker({ active }: { active: boolean }) {
  const { enabled } = useContext(MotionContext);
  return <AnimatePresence initial={false}>{active && <motion.i key="active" aria-hidden="true"
    className="motion-nav-marker" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
    layoutId={enabled ? "workspace-active-nav" : undefined}
    transition={{ ...springs.snappy, opacity: { duration: enabled ? motionTokens.duration.fast : 0 } }}/>}</AnimatePresence>;
}

const panelSelector = [
  ".page-heading", ".plans-hero", ".plans-summary", ".plans-list-panel",
  ".notifications-hero", ".notifications-summary-strip", ".notifications-stream-panel",
  ".notifications-side-panel", ".settings-tabs", ".settings-content",
  ".venture-header", ".venture-overview", ".venture-steps", ".venture-step-title",
  ".venture-main-panel", ".agent-main", ".data-search", ".data-content",
  ".shell > section", ".shell > .card",
].join(",");

/**
 * Progressive enhancement: server content is always visible, even without JS.
 * Animate actual mounted nodes, not keyed router children, so forms and nested
 * Next.js layouts retain their state. New tab panels are observed once.
 */
export function PageMotion({ children }: { children: ReactNode }) {
  const { enabled } = useContext(MotionContext);
  const pathname = usePathname();
  const query = useSearchParams().toString();
  const [scope, play] = useAnimate<HTMLDivElement>();
  useEffect(() => {
    const root = scope.current;
    if (!enabled || !root) return;
    const seen = new WeakSet<Element>();
    const active = new Map<HTMLElement, { cancel: () => void; restore: () => void }>();
    let disposed = false;
    let frame = 0;
    const reveal = (element: HTMLElement, index: number) => {
      const previous = active.get(element);
      if (previous) { previous.cancel(); previous.restore(); active.delete(element); }
      // Individual translate composes with the cards' CSS hover transform.
      // Do not leave an inline transform that would override hover feedback.
      element.classList.add("cm-reveal");
      const restore = () => { element.style.opacity = "1"; element.style.translate = "none"; };
      const controls = play(element, {
        opacity: [0.35, 1],
        translate: [`0px ${motionTokens.distance.md}px`, "0px 0px"],
      }, { duration: motionTokens.duration.slow, delay: Math.min(index, 5) * motionTokens.stagger, ease: motionTokens.easing.smooth });
      const handle = { cancel: () => controls.cancel(), restore };
      active.set(element, handle);
      void controls.then(() => {
        if (!disposed && active.get(element) === handle) { restore(); active.delete(element); }
      });
    };
    const observer = new IntersectionObserver(entries => {
      entries.filter(entry => entry.isIntersecting).forEach((entry, index) => {
        observer.unobserve(entry.target);
        reveal(entry.target as HTMLElement, index);
      });
    }, { threshold: 0.08 });
    const scan = () => {
      const explicit = root.querySelectorAll<HTMLElement>("[data-motion-enter], .console-page > .page-heading");
      const candidates = explicit.length ? [...explicit] : [...root.querySelectorAll<HTMLElement>(panelSelector)];
      const nodes = explicit.length ? candidates : candidates.filter(node =>
        node.hasAttribute("data-motion-key") ||
        (!node.querySelector("[data-motion-key]") && !node.parentElement?.closest(panelSelector)));
      nodes.forEach(node => {
        if (!seen.has(node)) { seen.add(node); observer.observe(node); }
      });
    };
    const mutations = new MutationObserver(records => {
      records.filter(record => record.type === "attributes").forEach(record => {
        const element = record.target as HTMLElement;
        const rect = element.getBoundingClientRect();
        if (rect.bottom > 0 && rect.top < window.innerHeight) reveal(element, 0);
      });
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(scan);
    });
    const finishFocused = (event: FocusEvent) => {
      active.forEach((control, node) => {
        if (node.contains(event.target as Node)) { control.cancel(); control.restore(); active.delete(node); }
      });
    };
    scan();
    mutations.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-motion-key"] });
    root.addEventListener("focusin", finishFocused);
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      mutations.disconnect();
      root.removeEventListener("focusin", finishFocused);
      active.forEach(control => { control.cancel(); control.restore(); });
    };
  }, [enabled, pathname, query, scope, play]);
  return <div ref={scope} className="motion-page">{children}</div>;
}

/** Real API values only; the accessible label always exposes the final value. */
export function AnimatedCount({ value }: { value: number | null }) {
  const { enabled } = useContext(MotionContext);
  const node = useRef<HTMLSpanElement>(null);
  const inView = useInView(node, { once: true });
  useEffect(() => {
    if (!node.current || value === null || !enabled || !inView) return;
    const target = node.current;
    const controls = animate(0, value, {
      duration: motionTokens.duration.crawl, ease: motionTokens.easing.smooth,
      onUpdate: current => { target.textContent = Math.round(current).toLocaleString("zh-CN"); },
    });
    return () => { controls.stop(); target.textContent = value.toLocaleString("zh-CN"); };
  }, [value, enabled, inView]);
  return <span className="motion-count" aria-label={value === null ? "暂未加载" : String(value)}>
    <span ref={node} aria-hidden="true">{value === null ? "—" : value.toLocaleString("zh-CN")}</span>
  </span>;
}
