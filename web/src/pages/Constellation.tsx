import { useEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { api, Dashboard } from "../api/client";
import { pageVariants } from "../motion/presets";

type Node = {
  id: string;
  skill: string;
  x: number;
  y: number;
  r: number;
  alpha: number;
};

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

export function Constellation() {
  const reduced = useReducedMotion();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .dashboard()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load constellation"));
  }, []);

  const nodes: Node[] = useMemo(() => {
    if (!data) return [];
    const bySkill = new Map<string, { sum: number; n: number }>();
    for (const row of data.skill_distribution) {
      const cur = bySkill.get(row.skill_id) ?? { sum: 0, n: 0 };
      bySkill.set(row.skill_id, {
        sum: cur.sum + row.proficiency * row.confidence,
        n: cur.n + 1,
      });
    }
    const entries = Array.from(bySkill.entries());
    return entries.map(([skill, agg], i) => {
      const h = hash(skill);
      const angle = ((h % 360) / 360) * Math.PI * 2 + i * 0.35;
      const rad = 0.22 + ((h >> 8) % 100) / 220;
      const strength = agg.n ? agg.sum / agg.n : 1;
      return {
        id: skill,
        skill,
        x: 0.5 + Math.cos(angle) * rad,
        y: 0.5 + Math.sin(angle) * rad * 0.72,
        r: 4 + Math.min(10, strength * 2.2),
        alpha: 0.35 + Math.min(0.55, strength / 8),
      };
    });
  }, [data]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !nodes.length) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let t0 = performance.now();

    const draw = (now: number) => {
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      const t = reduced ? 0 : (now - t0) / 1000;

      // faint links
      ctx.strokeStyle = "rgba(45, 212, 191, 0.12)";
      ctx.lineWidth = 1;
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i];
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          if (dx * dx + dy * dy > 0.12) continue;
          ctx.beginPath();
          ctx.moveTo(a.x * w, a.y * h);
          ctx.lineTo(b.x * w, b.y * h);
          ctx.stroke();
        }
      }

      for (const n of nodes) {
        const pulse = reduced ? 0 : Math.sin(t * 1.4 + hash(n.id) * 0.01) * 1.5;
        const x = n.x * w;
        const y = n.y * h;
        ctx.beginPath();
        ctx.fillStyle = `rgba(45, 212, 191, ${n.alpha})`;
        ctx.arc(x, y, n.r + pulse, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "rgba(232, 238, 244, 0.75)";
        ctx.font = "11px IBM Plex Sans, system-ui, sans-serif";
        ctx.fillText(n.skill.replace(/_/g, " "), x + n.r + 6, y + 4);
      }

      if (!reduced) raf = requestAnimationFrame(draw);
    };

    const resize = () => {
      const parent = canvas.parentElement;
      const w = parent?.clientWidth ?? 800;
      const h = Math.max(360, Math.min(520, Math.round(w * 0.48)));
      canvas.width = w * devicePixelRatio;
      canvas.height = h * devicePixelRatio;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
      draw(performance.now());
    };

    resize();
    window.addEventListener("resize", resize);
    if (!reduced) raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, [nodes, reduced]);

  return (
    <motion.div className="page" variants={pageVariants} initial="initial" animate="animate" exit="exit">
      <div className="panel">
        <h2 className="h2">Constellation</h2>
        <p className="lede">
          Decorative skill field derived from live matrix distribution — screenshot-worthy, evidence-coded.
        </p>
        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
        {!data && !error ? <p className="empty">Charting skills…</p> : null}
        {data ? (
          <div
            style={{
              border: "1px solid var(--line)",
              borderRadius: "var(--radius)",
              background: "rgba(12,16,20,0.55)",
              overflow: "hidden",
            }}
          >
            <canvas ref={canvasRef} aria-label="Skill constellation" />
            {reduced ? (
              <div style={{ padding: "0.75rem 1rem", fontSize: 13, color: "var(--ink-muted)" }}>
                Motion reduced — static constellation.
              </div>
            ) : null}
          </div>
        ) : null}
        {data && !nodes.length ? <p className="empty">No skill distribution points available.</p> : null}
      </div>
    </motion.div>
  );
}
