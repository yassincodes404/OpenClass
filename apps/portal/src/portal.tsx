import { useQuery } from "@tanstack/react-query";
import { NavLink, Route, Routes, useParams } from "react-router-dom";
import { useAuth } from "./auth";

const slug = "acme-support-phase-01-demo";
const sections = ["Overview", "Classifiers", "Observations", "Unknowns", "Discoveries", "Ontology", "Evaluations", "Integrations", "Usage & Billing", "Team & Access", "Settings"];

export type Workspace = { id: string; slug: string; name: string; role: string };

export function controlHeaders(token: string | undefined): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

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

function Projects() {
  const auth = useAuth();
  const workspaces = useQuery({
    queryKey: ["workspaces"],
    enabled: auth.ready && auth.authenticated,
    queryFn: async (): Promise<Workspace[]> => {
      const response = await fetch("/control/workspaces", { headers: controlHeaders(auth.token()) });
      if (response.status === 401) {
        auth.clearSession();
        throw new Error("Session expired");
      }
      if (!response.ok) throw new Error("Workspaces are temporarily unavailable");
      return response.json();
    },
  });

  if (!auth.ready) return <main><p className="lede">Checking secure session…</p></main>;
  if (!auth.authenticated) {
    return (
      <main className="access-gate">
        <p className="eyebrow">SECURE PORTAL / PHASE 2</p>
        <h1>Sign in to your workspace.</h1>
        <p className="lede">Projects are visible only to authorized workspace members.</p>
        <button onClick={() => void auth.login()}>Continue with Keycloak ↗</button>
      </main>
    );
  }

  return (
    <main>
      <p className="eyebrow">WORKSPACES / AUTHENTICATED</p>
      <h1>Projects</h1>
      {workspaces.isPending && <p className="lede">Loading workspaces…</p>}
      {workspaces.isError && <p className="lede">{(workspaces.error as Error).message}. Refresh to retry.</p>}
      {workspaces.isSuccess && workspaces.data.length === 0 && (
        <p className="lede">No workspaces yet. Create one via POST /control/workspaces, then reload.</p>
      )}
      {workspaces.data?.map((workspace) => (
        <article key={workspace.id} className="project-card">
          <p className="status"><i /> ACTIVE / {workspace.role.toUpperCase()}</p>
          <h2>{workspace.name}</h2>
          <p>Workspace slug <code>{workspace.slug}</code>. Product capabilities unlock across phases.</p>
          <NavLink to={`/projects/${workspace.slug}`}>Open workspace →</NavLink>
        </article>
      ))}
    </main>
  );
}

function Project() {
  const { section = "overview" } = useParams();
  return (
    <main>
      <div className="project-kicker">
        <div>
          <p className="eyebrow">ACME SUPPORT / PROJECT</p>
          <h1>{section === "overview" ? "The decision system, in focus." : section.replaceAll("-", " ")}</h1>
        </div>
        <span className="status"><i /> ACTIVE</span>
      </div>
      <nav className="section-nav" aria-label="Project navigation">
        {sections.map((item) => (
          <NavLink key={item} to={`/projects/${slug}/${item.toLowerCase().replaceAll(" & ", "-").replaceAll(" ", "-")}`}>{item}</NavLink>
        ))}
      </nav>
      <section className="signal">
        <p className="eyebrow">PHASE 2 / IDENTITY READY</p>
        <h2>Governed access starts here.</h2>
        <p>Workspace access is protected; product capabilities remain staged until their planned phases.</p>
      </section>
    </main>
  );
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
        <Route path="/projects/:id/:section?" element={<Project />} />
      </Routes>
    </>
  );
}
