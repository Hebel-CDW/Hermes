import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";

const ENTER = { duration: 0.22, ease: [0.22, 1, 0.36, 1] as const };

/** Fade + 8px rise on page enter. Honours prefers-reduced-motion. */
export function PageMotion({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion();
  const location = useLocation();
  return (
    <motion.div
      key={location.pathname}
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduce ? { duration: 0 } : ENTER}
    >
      {children}
    </motion.div>
  );
}

export function useMotionSafe() {
  const reduce = useReducedMotion();
  return {
    reduce: Boolean(reduce),
    fade: (delay = 0) =>
      reduce
        ? { initial: false as const, animate: { opacity: 1 }, transition: { duration: 0 } }
        : { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { ...ENTER, delay } },
    fadeOnly: (delay = 0) =>
      reduce
        ? { initial: false as const, animate: { opacity: 1 }, transition: { duration: 0 } }
        : { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { duration: 0.2, delay } },
  };
}
