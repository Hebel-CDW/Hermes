import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { BrandMark } from "../components/BrandMark";
import { transition } from "../motion/presets";

export function Entry() {
  return (
    <section
      className="page"
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: "2rem",
        textAlign: "center",
      }}
    >
      <div style={{ width: "min(920px, 100%)" }}>
        <BrandMark large />
        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...transition, delay: 0.45 }}
          style={{
            margin: "1.4rem auto 0",
            maxWidth: "34rem",
            fontSize: "clamp(1.05rem, 2.2vw, 1.35rem)",
            color: "var(--ink-muted)",
            lineHeight: 1.45,
          }}
        >
          Evidence-ranked workforce intelligence
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...transition, delay: 0.7 }}
          style={{ marginTop: "2.4rem", display: "flex", gap: "0.85rem", justifyContent: "center", flexWrap: "wrap" }}
        >
          <Link className="btn" to="/staff">
            Open console
          </Link>
          <Link className="btn btn-ghost" to="/matrix">
            View matrix
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
