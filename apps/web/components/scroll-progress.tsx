"use client";

import { useEffect, useRef } from "react";

/**
 * The 2px neon rule under the sticky header.
 *
 * Purely decorative — it duplicates information the scrollbar already carries,
 * so it is hidden from assistive technology rather than announced. The width is
 * written straight to the node instead of through React state: this runs on
 * every scroll frame and must not re-render the shell.
 */
export function ScrollProgress() {
  const fill = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let frame = 0;
    const paint = () => {
      frame = 0;
      const node = fill.current;
      if (!node) return;
      const doc = document.documentElement;
      const scrollable = doc.scrollHeight - doc.clientHeight;
      const ratio = scrollable > 0 ? doc.scrollTop / scrollable : 0;
      node.style.width = `${(Math.min(Math.max(ratio, 0), 1) * 100).toFixed(2)}%`;
    };
    const schedule = () => {
      if (frame || document.hidden) return;
      frame = requestAnimationFrame(paint);
    };
    paint();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule, { passive: true });
    document.addEventListener("visibilitychange", schedule);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      document.removeEventListener("visibilitychange", schedule);
    };
  }, []);

  return (
    <div className="h-0.5 bg-rule-hair" aria-hidden="true">
      <div ref={fill} className="h-full w-0 bg-neon" />
    </div>
  );
}
