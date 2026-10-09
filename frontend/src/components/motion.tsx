/**
 * Small motion primitives shared by every page.
 *
 * Deliberately CSS-driven: no animation library, so the bundle stays the same
 * size it was. Everything here degrades to an instant, fully visible state when
 * the OS asks for reduced motion, and `ScrollReveal` reveals itself on a timer
 * as well as on intersection so content can never get stuck invisible.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ElementType,
  type ReactNode,
} from "react";

/** Tracks the OS "reduce motion" setting and reacts to it changing live. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  });

  useEffect(() => {
    if (!window.matchMedia) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return reduced;
}

function supportsObserver(): boolean {
  return typeof window !== "undefined" && typeof window.IntersectionObserver === "function";
}

/**
 * Fades and lifts its children into view the first time they scroll on screen.
 * Falls back to "already visible" when IntersectionObserver is unavailable, when
 * motion is reduced, or after a safety timeout.
 */
export function ScrollReveal({
  children,
  className = "",
  animation = "anim-rise",
  delay = 0,
  as: Tag = "div",
  ...rest
}: {
  children: ReactNode;
  className?: string;
  animation?: "anim-rise" | "anim-fade" | "anim-pop" | "anim-slide-left";
  delay?: number;
  as?: ElementType;
} & Record<string, unknown>) {
  const ref = useRef<HTMLElement | null>(null);
  const reduced = usePrefersReducedMotion();
  const [shown, setShown] = useState(() => reduced || !supportsObserver());

  useEffect(() => {
    if (shown) return;
    const node = ref.current;
    if (!node) {
      setShown(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setShown(true);
          observer.disconnect();
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.05 },
    );
    observer.observe(node);

    // Belt and braces: never leave content hidden if the observer misbehaves.
    const failsafe = window.setTimeout(() => setShown(true), 1500);
    return () => {
      observer.disconnect();
      window.clearTimeout(failsafe);
    };
  }, [shown]);

  const style: CSSProperties = shown
    ? { animationDelay: `${delay}ms` }
    : { animationDelay: `${delay}ms`, opacity: 0 };

  const Component = Tag as ElementType;
  return (
    <Component
      ref={ref}
      className={shown ? `${animation} ${className}`.trim() : className}
      style={style}
      {...rest}
    >
      {children}
    </Component>
  );
}

/**
 * Applies the `stagger` class so direct children cascade in. Prefer putting this
 * on a real container in the page rather than wrapping every child by hand.
 */
export function Stagger({
  children,
  className = "",
  ...rest
}: { children: ReactNode; className?: string } & Record<string, unknown>) {
  return (
    <div className={`stagger ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}

/**
 * Counts a number up to its target when it first appears.
 *
 * Formatting is delegated to `format` so the caller stays in control of
 * currency and grouping; the same formatter runs on every frame.
 */
export function AnimatedNumber({
  value,
  format,
  duration = 900,
  className,
}: {
  value: number;
  format: (value: number) => string;
  duration?: number;
  className?: string;
}) {
  const reduced = usePrefersReducedMotion();
  const ref = useRef<HTMLSpanElement | null>(null);
  const [display, setDisplay] = useState(() => (reduced ? value : 0));
  const started = useRef(false);

  const run = useCallback(() => {
    if (started.current || reduced) return;
    started.current = true;

    const total = Number.isFinite(value) ? value : 0;
    let frame = 0;
    const step = (now: number) => {
      if (frame === 0) frame = now;
      const progress = Math.min(1, (now - frame) / duration);
      // easeOutExpo: fast first, then settles, so big numbers feel responsive.
      const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      setDisplay(total * eased);
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [value, duration, reduced]);

  useEffect(() => {
    if (reduced || started.current) {
      setDisplay(Number.isFinite(value) ? value : 0);
      return;
    }
    const node = ref.current;
    if (!node || !supportsObserver()) {
      run();
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          run();
          observer.disconnect();
        }
      },
      { threshold: 0.2 },
    );
    observer.observe(node);
    const failsafe = window.setTimeout(() => run(), 1500);
    return () => {
      observer.disconnect();
      window.clearTimeout(failsafe);
    };
  }, [value, run, reduced]);

  return (
    <span ref={ref} className={className}>
      {format(display)}
    </span>
  );
}
