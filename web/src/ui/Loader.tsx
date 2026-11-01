import { useEffect, useState } from "react";

/** Small spinning ring. Decorative: the surrounding element carries the accessible label. */
export function Spinner({ size = 18 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-hidden />;
}

/** Full-screen branded splash for the very first load (restoring a session). */
export function BootSplash({ message = "Getting your workspace ready" }: { message?: string }) {
  return (
    <div className="boot" role="status" aria-live="polite" aria-label="Restoring session">
      <div className="boot-mark" aria-hidden>
        <svg width="44" height="44" viewBox="0 0 40 40">
          <rect width="40" height="40" rx="8" fill="#fff" stroke="#e5e7eb" />
          <path d="M12 10v20M28 10v20" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
          <path d="M12 20h16" stroke="#b5122b" strokeWidth="3" strokeLinecap="round" />
        </svg>
      </div>
      <div className="boot-title">HERMES</div>
      <div className="boot-msg">{message}</div>
      <div className="progress-slide" aria-hidden>
        <span />
      </div>
    </div>
  );
}

/**
 * Multi-step "work in progress" card. The steps only describe what Hermes really does while the
 * request runs, and advance on a timer; the final step stays until the request finishes.
 */
export function StepLoader({ title, steps, every = 1100 }: { title: string; steps: string[]; every?: number }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => Math.min(n + 1, steps.length - 1)), every);
    return () => clearInterval(t);
  }, [steps.length, every]);
  return (
    <div className="step-loader" role="status" aria-live="polite" aria-label={title}>
      <div className="step-loader-head">
        <Spinner size={20} />
        <strong>{title}</strong>
      </div>
      <ol>
        {steps.map((s, k) => (
          <li key={s} className={k < i ? "done" : k === i ? "now" : ""}>
            <span className="tick" aria-hidden>
              {k < i ? "✓" : k === i ? "•" : ""}
            </span>
            {s}
          </li>
        ))}
      </ol>
      <div className="progress-slide" aria-hidden>
        <span />
      </div>
    </div>
  );
}

/** Copilot "thinking" indicator: cycling plain-English steps plus a gentle note when it is slow. */
export function Thinking({ steps }: { steps: string[] }) {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSecs((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const step = steps[Math.min(Math.floor(secs / 2.5), steps.length - 1)];
  return (
    <div className="thinking" role="status" aria-live="polite" aria-label="Hermes is thinking">
      <span className="dots" aria-hidden>
        <i />
        <i />
        <i />
      </span>
      <span>{step}</span>
      {secs >= 8 && <div className="thinking-note">Still working. The first answer after a restart takes longer while the model warms up.</div>}
    </div>
  );
}
