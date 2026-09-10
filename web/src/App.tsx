import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Entry } from "./pages/Entry";
import { Staff } from "./pages/Staff";
import { Learn } from "./pages/Learn";
import { Matrix } from "./pages/Matrix";
import { Constellation } from "./pages/Constellation";
import { Me } from "./pages/Me";

function ShellNav() {
  const loc = useLocation();
  if (loc.pathname === "/") return null;
  return (
    <nav className="nav">
      <NavLink to="/" className="nav-brand">
        HERMES
      </NavLink>
      <NavLink to="/staff" className={({ isActive }) => (isActive ? "active" : undefined)}>
        Staff
      </NavLink>
      <NavLink to="/learn" className={({ isActive }) => (isActive ? "active" : undefined)}>
        Learn
      </NavLink>
      <NavLink to="/matrix" className={({ isActive }) => (isActive ? "active" : undefined)}>
        Matrix
      </NavLink>
      <NavLink to="/constellation" className={({ isActive }) => (isActive ? "active" : undefined)}>
        Constellation
      </NavLink>
      <NavLink to="/me" className={({ isActive }) => (isActive ? "active" : undefined)}>
        Me
      </NavLink>
    </nav>
  );
}

export default function App() {
  const location = useLocation();
  return (
    <div className="app-shell">
      <div className="atmosphere" aria-hidden />
      <ShellNav />
      <AnimatePresence mode="wait">
        <motion.div key={location.pathname}>
          <Routes location={location}>
            <Route path="/" element={<Entry />} />
            <Route path="/staff" element={<Staff />} />
            <Route path="/learn" element={<Learn />} />
            <Route path="/matrix" element={<Matrix />} />
            <Route path="/constellation" element={<Constellation />} />
            <Route path="/me" element={<Me />} />
          </Routes>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
