"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  OpenClass,
  OpenClassError,
  type DecisionRun,
  type Project,
  type RunFeedback,
  type FeedbackAction,
} from "@openclass/sdk";
import { ProjectShell } from "../../shell";

const client = new OpenClass("");
const PAGE_SIZE = 50;

function formatTime(value: string) {
  return new Date(value).toLocaleString();
}

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export default function ProjectRunsPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [projectError, setProjectError] = useState("");
  const [runs, setRuns] = useState<DecisionRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [runsError, setRunsError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [provider, setProvider] = useState("");
  const [choice, setChoice] = useState("");
  const [supervision, setSupervision] = useState("");
  const [selected, setSelected] = useState<DecisionRun | null>(null);
  const [detailError, setDetailError] = useState("");
  const [feedbackList, setFeedbackList] = useState<RunFeedback[]>([]);
  const [feedbackAction, setFeedbackAction] = useState<FeedbackAction>("confirm");
  const [feedbackCorrectedChoice, setFeedbackCorrectedChoice] = useState("");
  const [feedbackNote, setFeedbackNote] = useState("");
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState("");

  const loadRuns = useCallback(
    async (offset: number) => {
      if (!id) return;
      offset === 0 ? setLoading(true) : setLoadingMore(true);
      setRunsError("");
      try {
        const page = await client.decisionRuns(id, { limit: PAGE_SIZE, offset });
        setRuns((current) => (offset === 0 ? page : [...current, ...page]));
        setHasMore(page.length === PAGE_SIZE);
      } catch {
        setRunsError("Could not load runs. Check the API connection and retry.");
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [id],
  );

  useEffect(() => {
    if (!id) return;
    client
      .project(id)
      .then(setProject)
      .catch((error: unknown) => {
        setProjectError(
          error instanceof OpenClassError && error.status === 404
            ? "Project not found."
            : "Could not load project. Check the API connection and retry.",
        );
      });
    void loadRuns(0);
  }, [id, loadRuns]);

  const filtered = useMemo(
    () =>
      runs.filter(
        (run) =>
          (!provider || run.provider === provider) &&
          (!choice || run.selected_choice === choice) &&
          (!supervision || run.supervision_outcome === supervision),
      ),
    [runs, provider, choice, supervision],
  );
  const providers = [...new Set(runs.map((run) => run.provider))].sort();
  const choices = [...new Set(runs.map((run) => run.selected_choice))].sort();

  async function inspect(run: DecisionRun) {
    setDetailError("");
    setSelected(run);
    setFeedbackMessage("");
    setFeedbackNote("");
    setFeedbackCorrectedChoice("");
    client
      .runFeedback({ project: id, runId: run.id })
      .then(setFeedbackList)
      .catch(() => setFeedbackList([]));
    try {
      setSelected(await client.decisionRun({ project: id, runId: run.id }));
    } catch {
      setDetailError("Could not refresh run details. Showing the loaded snapshot.");
    }
  }

  async function handleFeedbackSubmit(e: FormEvent) {
    e.preventDefault();
    if (!id || !selected) return;
    setFeedbackBusy(true);
    setFeedbackMessage("");
    try {
      const fb = await client.submitRunFeedback({
        project: id,
        runId: selected.id,
        action: feedbackAction,
        correctedChoice: feedbackAction === "correct" ? feedbackCorrectedChoice : undefined,
        note: feedbackNote || undefined,
      });
      setFeedbackList((prev) => [fb, ...prev]);
      setFeedbackMessage(
        feedbackAction === "correct" || feedbackAction === "missing_concept"
          ? "Feedback recorded! Evidence has been routed to the Evolution Inbox."
          : "Feedback recorded successfully.",
      );
      setFeedbackNote("");
      setFeedbackCorrectedChoice("");
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to submit feedback");
    } finally {
      setFeedbackBusy(false);
    }
  }

  if (projectError) {
    return (
      <main>
        <p className="empty" role="alert">
          {projectError}
        </p>
        <Link href="/projects">Projects</Link>
      </main>
    );
  }
  if (!project) {
    return (
      <main>
        <p className="empty" role="status">
          Loading project…
        </p>
      </main>
    );
  }

  return (
    <ProjectShell project={project} active="runs">
      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Runs</h2>
            <p className="muted">
              Persisted decision history for this project. Open a run to inspect the input, choices,
              provider, and supervision outcome.
            </p>
          </div>
          <button
            type="button"
            className="inspect-btn"
            onClick={() => void loadRuns(0)}
            disabled={loading}
          >
            Refresh
          </button>
        </div>

        {runs.length > 0 && (
          <div className="runs-filters">
            <label>
              Provider
              <select value={provider} onChange={(event) => setProvider(event.target.value)}>
                <option value="">All providers</option>
                {providers.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Choice
              <select value={choice} onChange={(event) => setChoice(event.target.value)}>
                <option value="">All choices</option>
                {choices.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Supervision
              <select value={supervision} onChange={(event) => setSupervision(event.target.value)}>
                <option value="">All outcomes</option>
                <option value="TRUSTED">Trusted</option>
                <option value="REVIEW">Review</option>
                <option value="UNKNOWN">Unknown</option>
              </select>
            </label>
          </div>
        )}

        {runsError && (
          <p role="alert" className="form-error">
            {runsError}{" "}
            <button type="button" className="inspect-btn" onClick={() => void loadRuns(0)}>
              Retry
            </button>
          </p>
        )}
        {loading ? (
          <p role="status" className="empty">
            Loading runs…
          </p>
        ) : runs.length === 0 && !runsError ? (
          <p className="empty">
            No runs yet.{" "}
            <Link href={`/projects/${project.slug}/data`}>
              Ingest data and run a decision service
            </Link>{" "}
            to see results here.
          </p>
        ) : filtered.length === 0 ? (
          <p className="empty">No loaded runs match these filters.</p>
        ) : (
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Input</th>
                  <th>Choice</th>
                  <th>Provider</th>
                  <th>Supervision</th>
                  <th>Latency</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((run) => (
                  <tr key={run.id}>
                    <td>{formatTime(run.created_at)}</td>
                    <td className="content-preview">{String(run.input_snapshot.content ?? "")}</td>
                    <td>
                      <strong>{run.selected_choice}</strong>
                    </td>
                    <td>
                      {run.provider}
                      {run.real_inference ? "" : " · Simulated"}
                    </td>
                    <td>{run.supervision_outcome}</td>
                    <td>{run.latency_ms.toFixed(0)} ms</td>
                    <td>
                      <button
                        type="button"
                        className="inspect-btn"
                        onClick={() => void inspect(run)}
                        aria-label={`Inspect run ${run.id}`}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {runs.length > 0 && (
          <div className="runs-footer">
            <span className="hint">
              Showing {filtered.length} of {runs.length} loaded runs. Filters apply to loaded runs.
            </span>
            {hasMore && (
              <button
                type="button"
                className="inspect-btn"
                onClick={() => void loadRuns(runs.length)}
                disabled={loadingMore}
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            )}
          </div>
        )}
      </section>

      {selected && (
        <section className="panel runs-detail" aria-label="Run details">
          <div className="section-heading">
            <h2>Run details</h2>
            <button type="button" className="inspect-btn" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          {detailError && (
            <p role="alert" className="form-error">
              {detailError}
            </p>
          )}
          <p className="hint">
            Run ID: {selected.id} · {formatTime(selected.created_at)}
          </p>
          <dl className="runs-detail-grid">
            <div>
              <dt>Selected choice</dt>
              <dd>{selected.selected_choice}</dd>
            </div>
            <div>
              <dt>Supervision</dt>
              <dd>
                {selected.supervision_outcome}: {selected.supervision_reason}
              </dd>
            </div>
            <div>
              <dt>Provider</dt>
              <dd>
                {selected.provider} / {selected.model} ·{" "}
                {selected.real_inference ? "Real inference" : "Simulated"}
              </dd>
            </div>
            <div>
              <dt>Execution mode</dt>
              <dd>{selected.execution_mode}</dd>
            </div>
            <div>
              <dt>Latency</dt>
              <dd>{selected.latency_ms.toFixed(1)} ms</dd>
            </div>
            <div>
              <dt>Decision service</dt>
              <dd>{selected.decision_service_id}</dd>
            </div>
          </dl>
          <h3>Input snapshot</h3>
          <p className="runs-input">{String(selected.input_snapshot.content ?? "")}</p>
          <p>
            <Link href={`/projects/${project.slug}/data`}>View source events</Link> · Event ID:{" "}
            <code>{selected.raw_event_id}</code>
          </p>
          <h3>Choice probabilities</h3>
          <ul className="runs-probabilities">
            {selected.choices_snapshot.map((item) => (
              <li key={item.key}>
                <span>
                  {item.label} ({item.key})
                </span>
                <strong>{percent(selected.probabilities[item.key] ?? 0)}</strong>
              </li>
            ))}
          </ul>
          <p className="hint">
            Top {percent(selected.top_probability)} · Margin {percent(selected.margin)} · UNKNOWN{" "}
            {percent(selected.unknown_probability)}
          </p>
          <h3>Instructions used</h3>
          <p className="runs-input">{selected.instructions_snapshot}</p>

          <h3 style={{ marginTop: "24px" }}>Human Feedback & Review</h3>
          {feedbackMessage && (
            <p style={{ color: "var(--accent)", fontSize: "13px", fontWeight: 600 }}>
              {feedbackMessage}
            </p>
          )}

          {feedbackList.length > 0 && (
            <div style={{ marginBottom: "16px" }}>
              <h4>Existing Feedback</h4>
              <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: "8px" }}>
                {feedbackList.map((fb) => (
                  <li
                    key={fb.id}
                    style={{
                      background: "var(--bg)",
                      border: "1px solid var(--line)",
                      padding: "8px 12px",
                      borderRadius: "6px",
                      fontSize: "13px",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <strong style={{ textTransform: "uppercase", color: "var(--accent)" }}>
                        {fb.action}
                      </strong>
                      <span style={{ color: "var(--muted)", fontSize: "11px" }}>
                        {new Date(fb.created_at).toLocaleString()}
                      </span>
                    </div>
                    {fb.corrected_choice && (
                      <p style={{ margin: "4px 0" }}>
                        Corrected choice: <code>{fb.corrected_choice}</code>
                      </p>
                    )}
                    {fb.note && <p style={{ margin: "4px 0", color: "var(--muted)" }}>{fb.note}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <form onSubmit={handleFeedbackSubmit} style={{ marginTop: "12px" }}>
            <div style={{ display: "grid", gap: "10px" }}>
              <div>
                <label
                  style={{
                    display: "block",
                    fontSize: "12px",
                    color: "var(--muted)",
                    marginBottom: "4px",
                  }}
                >
                  Feedback Action
                </label>
                <select
                  value={feedbackAction}
                  onChange={(e) => setFeedbackAction(e.target.value as FeedbackAction)}
                  style={{
                    width: "100%",
                    background: "var(--bg)",
                    color: "var(--text)",
                    border: "1px solid var(--line)",
                    padding: "8px 12px",
                    borderRadius: "6px",
                    fontSize: "13px",
                  }}
                >
                  <option value="confirm">Confirm (Decision is correct)</option>
                  <option value="correct">Correct (Change selected choice)</option>
                  <option value="missing_concept">Missing Concept (Route to Evolution)</option>
                  <option value="ambiguous">Ambiguous (Input unclear)</option>
                  <option value="out_of_domain">Out of Domain (Irrelevant inquiry)</option>
                  <option value="note">Note (Review observation)</option>
                </select>
              </div>

              {feedbackAction === "correct" && (
                <div>
                  <label
                    style={{
                      display: "block",
                      fontSize: "12px",
                      color: "var(--muted)",
                      marginBottom: "4px",
                    }}
                  >
                    Corrected Choice Key
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. ENTERPRISE or UNKNOWN"
                    value={feedbackCorrectedChoice}
                    onChange={(e) => setFeedbackCorrectedChoice(e.target.value)}
                    style={{
                      width: "100%",
                      background: "var(--bg)",
                      color: "var(--text)",
                      border: "1px solid var(--line)",
                      padding: "8px 12px",
                      borderRadius: "6px",
                      fontSize: "13px",
                    }}
                  />
                </div>
              )}

              <div>
                <label
                  style={{
                    display: "block",
                    fontSize: "12px",
                    color: "var(--muted)",
                    marginBottom: "4px",
                  }}
                >
                  Reviewer Note
                </label>
                <textarea
                  rows={2}
                  placeholder="Notes explaining your decision..."
                  value={feedbackNote}
                  onChange={(e) => setFeedbackNote(e.target.value)}
                  style={{
                    width: "100%",
                    background: "var(--bg)",
                    color: "var(--text)",
                    border: "1px solid var(--line)",
                    padding: "8px 12px",
                    borderRadius: "6px",
                    fontSize: "13px",
                  }}
                />
              </div>

              <div>
                <button
                  type="submit"
                  disabled={feedbackBusy}
                  style={{
                    padding: "8px 16px",
                    borderRadius: "6px",
                    background: "var(--accent)",
                    color: "#101411",
                    fontWeight: 600,
                    border: "none",
                    cursor: feedbackBusy ? "wait" : "pointer",
                    fontSize: "13px",
                  }}
                >
                  {feedbackBusy ? "Submitting…" : "Submit Run Feedback"}
                </button>
              </div>
            </div>
          </form>
        </section>
      )}
    </ProjectShell>
  );
}
