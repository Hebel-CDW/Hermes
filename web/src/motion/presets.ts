import type { Transition, Variants } from "framer-motion";

const reduced =
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export const transition: Transition = reduced
  ? { duration: 0.01 }
  : { duration: 0.55, ease: [0.22, 1, 0.36, 1] };

export const pageVariants: Variants = {
  initial: { opacity: 0, y: reduced ? 0 : 18 },
  animate: { opacity: 1, y: 0, transition },
  exit: { opacity: 0, y: reduced ? 0 : -12, transition: { duration: reduced ? 0.01 : 0.28 } },
};

export const stagger: Variants = {
  animate: {
    transition: { staggerChildren: reduced ? 0 : 0.08, delayChildren: reduced ? 0 : 0.05 },
  },
};

export const itemUp: Variants = {
  initial: { opacity: 0, y: reduced ? 0 : 16 },
  animate: { opacity: 1, y: 0, transition },
};

export const letter: Variants = {
  initial: { opacity: 0, y: reduced ? 0 : 40 },
  animate: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { ...transition, delay: reduced ? 0 : i * 0.05 },
  }),
};
