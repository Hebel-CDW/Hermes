import { FormEvent, useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { api, GapResult, Role } from "../api/client";
import { NarrateBanner } from "../components/NarrateBanner";
import { itemUp, pageVariants, stagger } from "../motion/presets";

export function Learn() {
  const reduced = useReducedMotion();
  const [roles, setRoles] = useState<Role[]>([]);
  const [identities, setIdentities] = useState<string[]>([]);
  const [roleId, setRoleId] = useState("");
  const [identity, setIdentity] = useState("");
  const [result, setResult] = useState<GapResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.roles(), api.identities()]).then(([r, i]) => {
      setRoles(r.roles);
      setIdentities(i.identities);
      if (r.roles[0]) setRoleId(r.roles[0].role_id);
      if (i.identities[0]) setIdentity(i.identities[0]);
    });
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const role = roles.find((r) => r.role_id === roleId);
    if (!role) return;
    setBusy(true);
    setError(null);
    try {
      const gaps = await api.gaps({
        coded_identity: identity,
        role_id: role.role_id,
        role_name: role.role_name,
        required_skills: role.required_skills,
      });
      setResult(gaps);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Gap computation failed");
    } finally {
      setBusy(false);
    }
  }

  const path = result ? [...result.gaps].sort((a, b) => b.demand_impact - a.demand_impact) : [];
  const maxImpact = Math.max(...path.map((g) => g.demand_impact), 0.001);

  return (
    <motion.div className="page" variants={pageVariants} initial="initial" animate="animate" exit="exit">
      <div className="panel">
        <h2 className="h2">Learn</h2>
        <p className="lede">Highest-impact skill gaps between a coded profile and a target role.</p>
        <NarrateBanner>
          Gap ranking is deterministic and demand-weighted. No names appear on this surface.
        </NarrateBanner>
        <form onSubmit={onSubmit}>
          <div className="form-row">
            <div className="field">
              <label htmlFor="identity">Coded identity</label>
              <select id="identity" value={identity} onChange={(e) => setIdentity(e.target.value)}>
                {identities.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="role">Target role</label>
              <select id="role" value={roleId} onChange={(e) => setRoleId(e.target.value)}>
                {roles.map((r) => (
                  <option key={r.role_id} value={r.role_id}>
                    {r.role_name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button className="btn" type="submit" disabled={busy || !identity || !roleId}>
            {busy ? "Computing…" : "Compute gaps"}
          </button>
        </form>
        {error ? <p style={{ color: "var(--danger)", marginTop: "1rem" }}>{error}</p> : null}
        <div style={{ marginTop: "2rem" }}>
          {!result ? (
            <p className="empty">Compute gaps to build a learning route.</p>
          ) : !path.length ? (
            <p className="empty">No grounded gaps returned by the engine.</p>
          ) : (
            <>
              <h3 style={{ fontFamily: "var(--font-display)", margin: "0 0 1rem" }}>Learning path</h3>
              <motion.ol
                variants={stagger}
                initial="initial"
                animate="animate"
                style={{ listStyle: "none", margin: 0, padding: 0, counterReset: "learn" }}
              >
                {path.map((g, idx) => (
                  <motion.li
                    key={g.skill_id}
                    variants={itemUp}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "3rem 1fr",
                      gap: "1rem",
                      marginBottom: "1.35rem",
                      alignItems: "start",
                    }}
                  >
                    <div
                      style={{
                        width: "2.5rem",
                        height: "2.5rem",
                        borderRadius: "50%",
                        border: "1px solid var(--amber)",
                        display: "grid",
                        placeItems: "center",
                        fontFamily: "var(--font-display)",
                        fontWeight: 700,
                        color: "var(--amber)",
                      }}
                    >
                      {idx + 1}
                    </div>
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                        <strong>{g.skill_id.replace(/_/g, " ")}</strong>
                        <span style={{ color: "var(--amber)" }}>
                          demand impact {g.demand_impact.toFixed(2)}
                        </span>
                      </div>
                      <div
                        style={{
                          marginTop: 8,
                          height: 8,
                          borderRadius: 999,
                          background: "rgba(232,238,244,0.08)",
                          overflow: "hidden",
                        }}
                      >
                        <motion.div
                          initial={reduced ? false : { width: 0 }}
                          animate={{ width: `${(g.demand_impact / maxImpact) * 100}%` }}
                          transition={{ duration: reduced ? 0.01 : 0.85, ease: [0.22, 1, 0.36, 1] }}
                          style={{
                            height: "100%",
                            background: "linear-gradient(90deg, var(--amber-dim), var(--amber))",
                          }}
                        />
                      </div>
                      <p style={{ margin: "0.45rem 0 0", color: "var(--ink-muted)", fontSize: 14 }}>
                        {g.reasoning}
                      </p>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                        level {g.current_level ?? "—"} → {g.required_level}
                      </div>
                    </div>
                  </motion.li>
                ))}
              </motion.ol>
            </>
          )}
        </div>
      </div>
    </motion.div>
  );
}
