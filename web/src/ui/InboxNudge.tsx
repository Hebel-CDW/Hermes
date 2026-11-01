import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { managerToolsApi } from "../api/endpoints";
import { useAuth } from "../lib/auth";
import { useCalm } from "./Fx";

const CHANGED = "hermes:inbox-changed";
/** Tell every badge to recount (after a decision is made). */
export const notifyInboxChanged = () => window.dispatchEvent(new Event(CHANGED));

/** How many things are waiting for this manager. Quiet by design: any failure just means "no badge". */
export function useInboxCount(): number {
  const { session } = useAuth();
  const { pathname } = useLocation();
  const [bump, setBump] = useState(0);
  useEffect(() => {
    const onChange = () => setBump((n) => n + 1);
    window.addEventListener(CHANGED, onChange);
    return () => window.removeEventListener(CHANGED, onChange);
  }, []);
  const staff = Boolean(session && (session.roles.includes("manager") || session.roles.includes("admin")));
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!staff) {
      setCount(0);
      return;
    }
    const c = new AbortController();
    managerToolsApi.inbox(c.signal).then(
      (i) => setCount(i.requests.length + i.contests.length),
      () => setCount(0),
    );
    return () => c.abort();
  }, [staff, session?.sub, pathname, bump]);
  return count;
}

/** A gentle prompt on the Overview when approvals are waiting. Renders nothing when there are none. */
export function InboxNudge() {
  const count = useInboxCount();
  const calm = useCalm();
  if (count === 0) return null;
  return (
    <motion.div
      className="nudge"
      role="status"
      initial={calm ? false : { opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
    >
      <span className="nudge-dot" aria-hidden />
      <span>
        <strong>{count}</strong> {count === 1 ? "thing is" : "things are"} waiting for your decision.
      </span>
      <Link className="btn btn-sm btn-primary" to="/inbox">
        Open approvals
      </Link>
    </motion.div>
  );
}
