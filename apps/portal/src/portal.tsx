import { Suspense, lazy } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import { ClassifierDetailPage, ClassifiersPage, ProjectOverview, Projects } from "./projects";
import { OpenWorldLoopStage } from "./open-world-stage";
import { ObservatoryArchitectureSections } from "./observatory-sections";
import "./landing.css";

const ProjectSettingsPage = lazy(() =>
  import("./security-pages").then((m) => ({ default: m.ProjectSettingsPage })),
);
const ProjectProvidersPage = lazy(() =>
  import("./security-pages").then((m) => ({ default: m.ProjectProvidersPage })),
);
const ProjectAuditPage = lazy(() =>
  import("./security-pages").then((m) => ({ default: m.ProjectAuditPage })),
);

const DataIngestPage = lazy(() =>
  import("./ingestion-pages").then((m) => ({ default: m.DataIngestPage })),
);
const ObservationsPage = lazy(() =>
  import("./ingestion-pages").then((m) => ({ default: m.ObservationsPage })),
);

const DecisionsPage = lazy(() =>
  import("./decision-pages").then((m) => ({ default: m.DecisionsPage })),
);
const DecisionServicePage = lazy(() =>
  import("./decision-pages").then((m) => ({ default: m.DecisionServicePage })),
);
const RunsPage = lazy(() => import("./decision-pages").then((m) => ({ default: m.RunsPage })));
const EvidencePage = lazy(() =>
  import("./evidence-page").then((m) => ({ default: m.EvidencePage })),
);

const UnknownsPage = lazy(() =>
  import("./unknowns-page").then((m) => ({ default: m.UnknownsPage })),
);
const ClustersPage = lazy(() =>
  import("./clusters-page").then((m) => ({ default: m.ClustersPage })),
);
const OntologyPage = lazy(() =>
  import("./ontology-page").then((m) => ({ default: m.OntologyPage })),
);
const AnalyticsPage = lazy(() => import("./analytics").then((m) => ({ default: m.AnalyticsPage })));
const IntegrationsPage = lazy(() =>
  import("./integrations-page").then((m) => ({ default: m.IntegrationsPage })),
);

const DiscoveriesPage = lazy(() =>
  import("./discoveries-page").then((m) => ({ default: m.DiscoveriesPage })),
);
const CandidateReviewPage = lazy(() =>
  import("./discoveries-page").then((m) => ({ default: m.CandidateReviewPage })),
);

const EvaluationsPage = lazy(() =>
  import("./evaluations-pages").then((m) => ({ default: m.EvaluationsPage })),
);
const DatasetPage = lazy(() =>
  import("./evaluations-pages").then((m) => ({ default: m.DatasetPage })),
);
const EvaluationDetailPage = lazy(() =>
  import("./evaluations-pages").then((m) => ({ default: m.EvaluationDetailPage })),
);

/**
 * OpenClass Portal Landing Experience (`<Home />`)
 * Owner: Abdelhamid Khaled (@AbdelhamidKhald)
 *
 * Public landing copy is illustrative; the workspace remains the live product.
 * Preserves all existing Portal navigation contracts (`<NavLink className="primary" to="/projects">Open workspace ↗</NavLink>`)
 * while making OpenClass's governed decision and discovery architecture visible,
 * interactive, and verifiable.
 */
function Home() {
  return (
    <main className="landing">
      <section className="oc-hero-grid" aria-label="OpenClass overview">
        <div className="oc-hero-copy">
          <p className="eyebrow">THE OPEN-WORLD CLASSIFICATION ENGINE</p>
          <h1>
            Make room for <br />
            the <em>unknown.</em>
          </h1>
          <p className="lede">
            Classify what you know. Keep uncertainty as evidence. Review changes before they become
            your next version.
          </p>
          <div className="oc-cta-row">
            <NavLink className="primary" to="/projects">
              Open workspace ↗
            </NavLink>
            <a className="ghost-link" href="#open-world-loop">
              Try the loop
            </a>
          </div>
        </div>
        <aside className="oc-hero-example" aria-label="Simulated classification example">
          <p className="oc-example-label">A SMALL EXAMPLE. A DIFFERENT OUTCOME.</p>
          <blockquote>“Cancel my plan.”</blockquote>
          <div className="oc-example-choices" aria-label="Available classes">
            <span>billing</span>
            <span>technical</span>
            <span>sales</span>
          </div>
          <div className="oc-example-result">
            <span aria-hidden="true">↳</span>
            <div>
              <strong>UNKNOWN</strong>
              <p>Not a bad guess. A useful signal.</p>
            </div>
          </div>
          <p className="oc-example-caption">
            Simulated example with a three-class ontology. Unknown does not automatically mean a new
            class.
          </p>
        </aside>
      </section>

      <div className="oc-product-principles" aria-label="OpenClass principles">
        <span>Local first</span>
        <span>Provider independent</span>
        <span>Human-approved evolution</span>
        <a href="#quickstart">Run it locally ↗</a>
      </div>

      <OpenWorldLoopStage />
      <ObservatoryArchitectureSections />

      <section className="oc-closing-banner" aria-label="Get started with OpenClass">
        <div>
          <h2>Your classes are a starting point.</h2>
          <p>Keep the evidence. Make the next decision with more context.</p>
        </div>
        <div className="oc-cta-row">
          <NavLink className="primary" to="/projects">
            Open workspace ↗
          </NavLink>
          <a className="ghost-link" href="https://github.com/yassincodes404/OpenClass">
            Read the source
          </a>
        </div>
      </section>

      <footer className="oc-portal-footer">
        <span>OpenClass. Start with what you know.</span>
        <a href="https://github.com/yassincodes404/OpenClass/blob/main/LICENSE">
          Open source · AGPL-3.0-only
        </a>
      </footer>
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
      <NavLink to="/" className="brand">
        <strong>O↗</strong> OPENCLASS
      </NavLink>
      <nav>
        <NavLink to="/">Home</NavLink>
        <NavLink to="/projects">Projects</NavLink>
      </nav>
      {auth.authenticated && (
        <button className="sign-out" onClick={() => void auth.logout()}>
          Sign out
        </button>
      )}
      <span className="badge">GENESIS / PORTAL</span>
    </header>
  );
}

export function Portal() {
  const { pathname } = useLocation();
  return (
    <div className={`portal-shell${pathname === "/" ? " is-landing" : ""}`}>
      <Header />
      <Suspense fallback={<div className="panel">Loading workspace module…</div>}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/:projectId" element={<ProjectOverview />} />
          <Route path="/projects/:projectId/classifiers" element={<ClassifiersPage />} />
          <Route
            path="/projects/:projectId/classifiers/:classifierId"
            element={<ClassifierDetailPage />}
          />
          <Route path="/projects/:projectId/data" element={<DataIngestPage />} />
          <Route path="/projects/:projectId/observations" element={<ObservationsPage />} />
          <Route path="/projects/:projectId/evaluations" element={<EvaluationsPage />} />
          <Route
            path="/projects/:projectId/evaluations/datasets/:datasetId"
            element={<DatasetPage />}
          />
          <Route
            path="/projects/:projectId/evaluations/runs/:evaluationId"
            element={<EvaluationDetailPage />}
          />
          <Route path="/projects/:projectId/decisions" element={<DecisionsPage />} />
          <Route
            path="/projects/:projectId/decisions/:serviceId"
            element={<DecisionServicePage />}
          />
          <Route path="/projects/:projectId/runs" element={<RunsPage />} />
          <Route path="/projects/:projectId/evidence" element={<EvidencePage />} />
          <Route path="/projects/:projectId/unknowns" element={<UnknownsPage />} />
          <Route path="/projects/:projectId/unknowns/clusters" element={<ClustersPage />} />
          <Route path="/projects/:projectId/analytics" element={<AnalyticsPage />} />
          <Route path="/projects/:projectId/ontology" element={<OntologyPage />} />
          <Route path="/projects/:projectId/discoveries" element={<DiscoveriesPage />} />
          <Route
            path="/projects/:projectId/discoveries/:candidateId"
            element={<CandidateReviewPage />}
          />
          <Route path="/projects/:projectId/integrations" element={<IntegrationsPage />} />
          <Route path="/projects/:projectId/settings" element={<ProjectSettingsPage />} />
          <Route path="/projects/:projectId/providers" element={<ProjectProvidersPage />} />
          <Route path="/projects/:projectId/audit" element={<ProjectAuditPage />} />
        </Routes>
      </Suspense>
    </div>
  );
}
