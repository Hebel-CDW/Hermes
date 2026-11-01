import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { Role } from "./api/types";
import { hasRole, useAuth } from "./lib/auth";
import { NameProvider } from "./lib/names";
import { SkillProvider } from "./lib/skills";
import { homeFor } from "./routes";
import { WelcomeGuide } from "./ui/Guide";
import { Shell } from "./ui/Shell";
import { BootSplash } from "./ui/Loader";
import { EmptyState } from "./ui/States";
import Capability from "./views/Capability";
import Compare from "./views/Compare";
import Growth from "./views/Growth";
import Inbox from "./views/Inbox";
import RoleLab from "./views/RoleLab";
import TeamGrid from "./views/TeamGrid";
import DataQuality from "./views/DataQuality";
import CandidateDetail from "./views/CandidateDetail";
import Insights from "./views/Insights";
import Learning from "./views/Learning";
import Login from "./views/Login";
import Matrix from "./views/Matrix";
import NotFound from "./views/NotFound";
import Overview from "./views/Overview";
import Profile from "./views/Profile";
import RequestDetail from "./views/RequestDetail";
import Requests from "./views/Requests";
import Skills from "./views/Skills";
import SkillUpdate from "./views/SkillUpdate";
import Workforce from "./views/Workforce";

const STAFF: Role[] = ["manager", "admin"];
const MANAGER: Role[] = ["manager"];
const ANY: Role[] = ["employee", "manager", "admin"];
const EMPLOYEE: Role[] = ["employee"];

function Guard({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { session } = useAuth();
  if (!hasRole(session, ...roles)) {
    return (
      <EmptyState title="Not available for your role">
        This page requires the {roles.join(" or ")} role. Access is enforced by the server; navigation only reflects it.
      </EmptyState>
    );
  }
  return <>{children}</>;
}

export default function App() {
  const { session } = useAuth();
  const location = useLocation();

  if (session === undefined) {
    return (
      <BootSplash message="Restoring your session" />
    );
  }
  if (session === null) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace state={{ from: location.pathname + location.search }} />} />
      </Routes>
    );
  }

  const page = (roles: Role[], el: ReactNode) => <Guard roles={roles}>{el}</Guard>;
  return (
    <NameProvider>
    <SkillProvider>
    <WelcomeGuide />
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="*"
        element={
          <Shell>
            <Routes>
              <Route path="/" element={<Navigate to={homeFor(session.roles)} replace />} />
              <Route path="/overview" element={page(STAFF, <Overview />)} />
              <Route path="/workforce" element={page(STAFF, <Workforce />)} />
              <Route path="/skills" element={page(STAFF, <Skills />)} />
              <Route path="/matrix" element={page(STAFF, <Matrix />)} />
              <Route path="/update-skills" element={page(STAFF, <SkillUpdate />)} />
              <Route path="/requests" element={page(MANAGER, <Requests />)} />
              <Route path="/requests/:id" element={page(MANAGER, <RequestDetail />)} />
              <Route path="/requests/:id/compare" element={page(MANAGER, <Compare />)} />
              <Route path="/inbox" element={page(STAFF, <Inbox />)} />
              <Route path="/team-grid" element={page(STAFF, <TeamGrid />)} />
              <Route path="/role-lab" element={page(MANAGER, <RoleLab />)} />
              <Route path="/growth" element={page(EMPLOYEE, <Growth />)} />
              <Route path="/capability" element={page(MANAGER, <Capability />)} />
              <Route path="/capability/:id" element={page(MANAGER, <CandidateDetail />)} />
              <Route path="/learning" element={page(ANY, <Learning />)} />
              <Route path="/data-quality" element={page(STAFF, <DataQuality />)} />
              <Route path="/insights" element={page(STAFF, <Insights />)} />
              <Route path="/profile" element={page(ANY, <Profile />)} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Shell>
        }
      />
    </Routes>
    </SkillProvider>
    </NameProvider>
  );
}
