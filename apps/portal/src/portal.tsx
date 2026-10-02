import { NavLink, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { ClassifierDetailPage, ClassifiersPage, ProjectOverview, Projects } from "./projects";
import { ProjectAuditPage, ProjectProvidersPage, ProjectSettingsPage } from "./security-pages";
import { DataIngestPage, ObservationsPage } from "./ingestion-pages";

function Home() {
  return (
    <main className="landing">
      <p className="eyebrow">OPENCLASS / GOVERNED DECISIONS</p>
      <h1>Turn uncertainty into <em>evidence.</em></h1>
      <p className="lede">A secure portal for teams that refuse to force uncertain requests into the wrong workflow.</p>
      <NavLink className="primary" to="/projects">Open workspace ↗</NavLink>
    </main>
  );
}

function Placeholder({ label }: { label: string }) {
  return (
    <section className="signal">
      <p className="eyebrow">STAGED / UPCOMING PHASE</p>
      <h2>{label} arrives in its planned phase.</h2>
      <p>Workspace access is protected; this capability is not claimed until its phase ships.</p>
    </section>
  );
}

export function ProjectPlaceholder({ label }: { label: string }) {
  return <Placeholder label={label} />;
}

function Header() {
  const auth = useAuth();
  return (
    <header>
      <NavLink to="/" className="brand"><strong>O↗</strong> OPENCLASS</NavLink>
      <nav><NavLink to="/">Home</NavLink><NavLink to="/projects">Projects</NavLink></nav>
      {auth.authenticated && <button className="sign-out" onClick={() => void auth.logout()}>Sign out</button>}
      <span className="badge">GENESIS / PORTAL</span>
    </header>
  );
}

export function Portal() {
  return (
    <>
      <Header />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/:projectId" element={<ProjectOverview />} />
        <Route path="/projects/:projectId/classifiers" element={<ClassifiersPage />} />
        <Route path="/projects/:projectId/classifiers/:classifierId" element={<ClassifierDetailPage />} />
        <Route path="/projects/:projectId/data" element={<DataIngestPage />} />
        <Route path="/projects/:projectId/observations" element={<ObservationsPage />} />
        <Route path="/projects/:projectId/unknowns" element={<Placeholder label="The UNKNOWN workspace" />} />
        <Route path="/projects/:projectId/discoveries" element={<Placeholder label="Discovery & canonicalization" />} />
        <Route path="/projects/:projectId/settings" element={<ProjectSettingsPage />} />
        <Route path="/projects/:projectId/providers" element={<ProjectProvidersPage />} />
        <Route path="/projects/:projectId/audit" element={<ProjectAuditPage />} />
      </Routes>
    </>
  );
}
