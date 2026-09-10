import { motion } from "framer-motion";
import { letter } from "../motion/presets";

const WORD = "HERMES";

export function BrandMark({ large = false }: { large?: boolean }) {
  return (
    <motion.h1
      aria-label="Hermes"
      style={{
        fontFamily: "var(--font-display)",
        fontWeight: 800,
        letterSpacing: large ? "0.18em" : "0.12em",
        fontSize: large ? "clamp(3.5rem, 14vw, 8rem)" : "1.1rem",
        margin: 0,
        display: "flex",
        gap: large ? "0.04em" : "0.02em",
        lineHeight: 0.95,
      }}
      initial="initial"
      animate="animate"
    >
      {WORD.split("").map((ch, i) => (
        <motion.span key={`${ch}-${i}`} custom={i} variants={letter} style={{ display: "inline-block" }}>
          {ch}
        </motion.span>
      ))}
    </motion.h1>
  );
}
