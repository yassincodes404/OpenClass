import { NavLink, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { ClassifierDetailPage, ClassifiersPage, ProjectOverview, Projects } from "./projects";
import { ProjectAuditPage, ProjectProvidersPage, ProjectSettingsPage } from "./security-pages";
import { DataIngestPage, ObservationsPage } from "./ingestion-pages";
import { DecisionServicePage, DecisionsPage, RunsPage } from "./decision-pages";
import { UnknownsPage } from "./unknowns-page";
import { ClustersPage } from "./clusters-page";
import { OntologyPage } from "./ontology-page";
import { AnalyticsPage } from "./analytics";
import { IntegrationsPage } from "./integrations-page";
import { CandidateReviewPage, DiscoveriesPage } from "./discoveries-page";
import { DatasetPage, EvaluationDetailPage, EvaluationsPage } from "./evaluations-pages";
import { ObservatoryArchitectureSections, OpenWorldLoopStage } from "./open-world-stage";

/**
 * OpenClass Portal Landing Experience (`<Home />`)
 * Owner: Abdelhamid Khaled (@AbdelhamidKhald)
 *
 * Design Paradigm: "Botanical Telemetry / Precision Observatory"
 * Preserves all existing Portal navigation contracts (`<NavLink className="primary" to="/projects">Open workspace ↗</NavLink>`)
 * while making OpenClass's governed decision and discovery architecture visible,
 * interactive, and verifiable.
 */
function Home() {
  return (
    <main className="landing">
      {/* Live Telemetry & Invariant Provenance Ribbon */}
      <div className="oc-telemetry-ribbon" aria-label="Genesis platform provenance">
        <span className="oc-ribbon-badge">GENESIS v0.0.1 · AGPL-3.0</span>
        <span className="oc-ribbon-item">
          <i>●</i> UNKNOWN IS PERMANENT
        </span>
        <span className="oc-ribbon-item">
          <i>●</i> PREDICTIONS ≠ GROUND TRUTH
        </span>
        <span className="oc-ribbon-item">
          <i>●</i> APPEND-ONLY ONTOLOGY SNAPSHOTS
        </span>
      </div>

      {/* Hero Split: Narrative + Closed-World vs. Open-World Comparison */}
      <section className="oc-hero-grid" aria-label="OpenClass overview">
        <div className="oc-hero-copy">
          <p className="eyebrow">
            OPENCLASS / GOVERNED DECISIONS · THE OPEN-WORLD CLASSIFICATION ENGINE
          </p>
          <h1>
            Start with what you know. Discover what you don’t.{" "}
            <span className="oc-hero-subline">
              Turn uncertainty into <em>evidence.</em>
            </span>
          </h1>
          <p className="lede">
            A secure portal for teams that refuse to force uncertain requests into the wrong
            workflow. Fast bounded models handle what your active ontology supports, unfamiliar
            inputs persist as first-class <code>UNKNOWN</code> evidence, and Teacher proposals pass
            replay evaluation and human review before becoming versioned knowledge.
          </p>

          <div className="oc-cta-row">
            <NavLink className="primary" to="/projects">
              Open workspace ↗
            </NavLink>
            <a className="ghost-link" href="#open-world-loop">
              Inspect decision loop ↓
            </a>
            <a className="mono-link" href="#quickstart">
              $ docker compose up · Quickstart
            </a>
          </div>

          <div className="oc-invariant-pills">
            <span className="oc-inv-pill">
              <strong>FAST PATH</strong> Jev · Laya · Mock
            </span>
            <span className="oc-inv-pill">
              <strong>ABSTENTION</strong> First-class UNKNOWN pool
            </span>
            <span className="oc-inv-pill">
              <strong>SUPERVISION</strong> Advisory reviews (OC-016)
            </span>
            <span className="oc-inv-pill">
              <strong>GOVERNANCE</strong> Replay-gated vN+1 (OC-008/009)
            </span>
          </div>
        </div>

        {/* Right Column: Closed-World Guess vs. OpenClass Governed Decision */}
        <aside className="oc-contrast-card" aria-label="Closed-world vs open-world comparison">
          <div className="oc-contrast-head">
            <span>OBSERVATION TRACE</span>
            <code>“Cancel my plan”</code>
          </div>
          <p className="oc-contrast-context">
            Active Ontology <code>v1</code> knows only <code>{"{billing, technical, sales}"}</code>:
          </p>

          <div className="oc-contrast-box bad">
            <div className="oc-contrast-box-top">
              <span className="oc-tone-chip tone-error">CLOSED-WORLD CLASSIFIER</span>
              <code>FORCED GUESS</code>
            </div>
            <strong>Routes to billing (0.54)</strong>
            <p>
              Forces an unsupported cancellation request into the least-wrong label, triggering an
              invoice workflow and hiding the missing concept.
            </p>
          </div>

          <div className="oc-contrast-box good">
            <div className="oc-contrast-box-top">
              <span className="oc-tone-chip tone-known">OPENCLASS GOVERNED ENGINE</span>
              <code>DISCIPLINED ABSTENTION</code>
            </div>
            <strong>Selects UNKNOWN (0.950) → Evidence Pool</strong>
            <p>
              Preserves the full distribution, isolates the observation for clustering, and proposes
              candidate <code>cancellation</code> gated by replay evaluation and human approval.
            </p>
          </div>
        </aside>
      </section>

      {/* Signature Interactive Animated Scene */}
      <OpenWorldLoopStage />

      {/* Fast vs Slow Path, 6 Invariants, Grounded Proofs, Honest Matrix & Quickstart */}
      <ObservatoryArchitectureSections />

      {/* Closing CTA Banner & Architectural Footer */}
      <section className="oc-closing-banner" aria-label="Get started with OpenClass">
        <div>
          <p className="eyebrow">READY FOR GOVERNED EVOLUTION</p>
          <h2>Refuse to force uncertain reality into the wrong workflow.</h2>
          <p className="muted">
            Inspect projects, classifiers, decision runs, unknown clusters, and provider governance
            in the workspace.
          </p>
        </div>
        <div className="oc-cta-row">
          <NavLink className="primary" to="/projects">
            Open Project Workspace ↗
          </NavLink>
          <a className="ghost-link" href="#open-world-loop">
            Back to decision stage ↑
          </a>
        </div>
      </section>

      <footer className="oc-portal-footer">
        <span>Local first. Provider independent. Evidence driven.</span>
        <span>
          v0.0.1 Genesis Foundation · AGPL-3.0-only · No secrets in logs, errors, or events.
        </span>
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
  return (
    <>
      <Header />
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
        <Route path="/projects/:projectId/decisions/:serviceId" element={<DecisionServicePage />} />
        <Route path="/projects/:projectId/runs" element={<RunsPage />} />
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
    </>
  );
}
