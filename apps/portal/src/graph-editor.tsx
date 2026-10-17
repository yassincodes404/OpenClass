import { useState, type FormEvent } from "react";
import type { DecisionGraphInput, DecisionNodeInput, DecisionService } from "@openclass/sdk";

function DecisionGraphCanvas({ graph }: { graph: DecisionGraphInput }) {
  const nodes = graph.nodes;
  if (!nodes.length) return null;
  const colW = 240;
  const startX = 28;
  const nodeW = 190;
  const nodeH = 98;
  const nodeY = 36;
  const svgW = Math.max(720, startX * 2 + nodes.length * colW);
  const svgH = 200;

  return (
    <div className="decision-graph-canvas" aria-hidden="true">
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        style={{ width: "100%", height: "auto", display: "block" }}
      >
        <defs>
          <marker
            id="dg-arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 10 5 L 0 9 z" fill="rgba(198,242,119,0.75)" />
          </marker>
        </defs>
        {graph.transitions.map((t, idx) => {
          const fromIdx = nodes.findIndex((n) => n.id === t.from_node_key);
          const toIdx = nodes.findIndex((n) => n.id === t.to_node_key);
          if (fromIdx < 0 || toIdx < 0) return null;
          const x1 = startX + fromIdx * colW + nodeW;
          const y1 = nodeY + 34 + (idx % 3) * 14;
          const x2 = startX + toIdx * colW;
          const y2 = nodeY + 48;
          const midX = (x1 + x2) / 2;
          return (
            <g key={`${t.from_node_key}-${t.choice_key}-${idx}`}>
              <path
                d={`M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`}
                fill="none"
                stroke={t.require_approval ? "rgba(215,180,248,0.78)" : "rgba(198,242,119,0.6)"}
                strokeWidth="2"
                strokeDasharray={t.require_approval ? "4 3" : undefined}
                markerEnd="url(#dg-arrow)"
              />
              <rect
                x={midX - 38}
                y={(y1 + y2) / 2 - 10}
                width="76"
                height="18"
                rx="4"
                fill="rgba(9,15,12,0.92)"
                stroke="rgba(220,238,226,0.18)"
              />
              <text
                x={midX}
                y={(y1 + y2) / 2 + 2}
                textAnchor="middle"
                fill="#edf3ee"
                fontSize="9"
                fontFamily="var(--mono)"
              >
                {(t.choice_key || "EDGE").slice(0, 10)}
              </text>
            </g>
          );
        })}
        {nodes.map((node, index) => {
          const x = startX + index * colW;
          const knownCount = node.choices.filter((c) => c.key !== "UNKNOWN").length;
          return (
            <g key={node.id ?? index} transform={`translate(${x}, ${nodeY})`}>
              <rect
                width={nodeW}
                height={nodeH}
                rx="10"
                fill="rgba(19, 28, 23, 0.94)"
                stroke={index === 0 ? "rgba(198,242,119,0.55)" : "rgba(220,238,226,0.2)"}
                strokeWidth="1.5"
              />
              <text
                x="12"
                y="20"
                fill="rgba(198,242,119,0.9)"
                fontSize="9.5"
                fontFamily="var(--mono)"
              >
                {index === 0 ? "ENTRYPOINT · NODE 01" : `NODE 0${index + 1}`}
              </text>
              <text x="12" y="38" fill="#edf3ee" fontSize="12.5" fontWeight="600">
                {(node.name || `Node ${index + 1}`).slice(0, 20)}
              </text>
              <text
                x="12"
                y="56"
                fill="rgba(164,180,168,0.85)"
                fontSize="10"
                fontFamily="var(--mono)"
              >
                {knownCount} known · {(node.risk_level ?? "ordinary").toUpperCase()}
              </text>
              <rect
                x="10"
                y="68"
                width={nodeW - 20}
                height="20"
                rx="5"
                fill="rgba(242,200,121,0.12)"
                stroke="rgba(242,200,121,0.38)"
              />
              <text x="18" y="81" fill="#f2c879" fontSize="9.5" fontFamily="var(--mono)">
                FALLBACK: LOCKED
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function initialGraph(service: DecisionService): DecisionGraphInput {
  const nodes = structuredClone(service.nodes);
  const key = (value: string) => nodes.find((n) => n.id === value || n.name === value)?.id ?? value;
  const transitions = (service.transitions ?? []).map((t) => ({
    ...t,
    from_node_key: key(t.from_node_key),
    to_node_key: key(t.to_node_key),
  }));
  // Normalize legacy choice targets to the same editable transition list.
  // Explicit transitions take precedence, as they do on the server.
  for (const node of nodes) {
    for (const choice of node.choices) {
      const target = choice.target_node_id ?? choice.target_node_name;
      if (
        target &&
        !transitions.some((t) => t.from_node_key === node.id && t.choice_key === choice.key)
      )
        transitions.push({
          from_node_key: node.id,
          choice_key: choice.key,
          to_node_key: key(target),
          require_approval: false,
        });
      choice.target_node_id = null;
      choice.target_node_name = null;
    }
  }
  return { nodes, transitions };
}

/** Shared form only: all persistence, graph validity and version authority remain on the server. */
export function GraphEditor({
  service,
  onSave,
}: {
  service: DecisionService;
  onSave: (graph: DecisionGraphInput) => Promise<void>;
}) {
  const [graph, updateGraph] = useState(() => initialGraph(service));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  function setGraph(update: (graph: DecisionGraphInput) => DecisionGraphInput) {
    setSaved(false);
    updateGraph(update);
  }
  function editNode(index: number, changes: Partial<DecisionNodeInput>) {
    setGraph((g) => ({
      ...g,
      nodes: g.nodes.map((n, i) => (i === index ? { ...n, ...changes } : n)),
    }));
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSaved(false);
    const names = graph.nodes.map((n) => n.name.trim());
    if (new Set(names).size !== names.length) {
      setError("Node names must be unique.");
      return;
    }
    for (const node of graph.nodes) {
      const keys = node.choices.map((c) => c.key);
      if (new Set(keys).size !== keys.length || !keys.includes("UNKNOWN") || keys.length < 2) {
        setError("Every node needs unique choice keys, a known choice and permanent UNKNOWN.");
        return;
      }
    }
    if (
      graph.transitions.some(
        (t) =>
          !graph.nodes.some((n) => n.id === t.from_node_key) ||
          !graph.nodes.some((n) => n.id === t.to_node_key),
      )
    ) {
      setError("Remove transitions to deleted nodes before saving.");
      return;
    }
    setBusy(true);
    try {
      await onSave(graph);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Graph was not saved.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save} className="panel workflow" aria-label="Decision graph editor">
      <h3>Decision graph</h3>
      <p>
        Version {service.version_number ?? "unavailable"} · first node is the entrypoint. Saving
        creates a new immutable version; historical runs keep their pinned version.
      </p>
      <p>
        UNKNOWN is permanent and does not grant execution authority. Server policy and human
        approval still apply.
      </p>
      <DecisionGraphCanvas graph={graph} />
      {graph.nodes.map((node, index) => (
        <fieldset key={node.id ?? index} disabled={busy}>
          <legend>
            Node {index + 1}
            {index === 0 ? " · entrypoint" : ""}
          </legend>
          <label>
            Node name
            <input
              required
              maxLength={100}
              value={node.name}
              onChange={(e) => editNode(index, { name: e.target.value })}
            />
          </label>
          <label>
            Node instructions
            <textarea
              required
              maxLength={2000}
              value={node.instructions}
              onChange={(e) => editNode(index, { instructions: e.target.value })}
            />
          </label>
          <label>
            Risk level
            <select
              value={node.risk_level ?? "ordinary"}
              onChange={(e) =>
                editNode(index, { risk_level: e.target.value as "ordinary" | "high" })
              }
            >
              <option value="ordinary">Ordinary</option>
              <option value="high">High</option>
            </select>
          </label>
          <label>
            Minimum margin (blank: server policy)
            <input
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={node.min_margin ?? ""}
              onChange={(e) =>
                editNode(index, {
                  min_margin: e.target.value === "" ? null : Number(e.target.value),
                })
              }
            />
          </label>
          <label>
            Maximum UNKNOWN probability (blank: server policy)
            <input
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={node.max_unknown_probability ?? ""}
              onChange={(e) =>
                editNode(index, {
                  max_unknown_probability: e.target.value === "" ? null : Number(e.target.value),
                })
              }
            />
          </label>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={node.pause_on_review ?? false}
              onChange={(e) => editNode(index, { pause_on_review: e.target.checked })}
            />{" "}
            Pause for human review
          </label>
          {node.choices.map((choice, ci) => {
            const locked = choice.key === "UNKNOWN";
            const transition = graph.transitions.find(
              (t) => t.from_node_key === node.id && t.choice_key === choice.key,
            );
            return (
              <fieldset key={`${node.id}-${ci}`}>
                <legend>
                  {locked ? "UNKNOWN · permanent fallback (locked)" : `Choice ${ci + 1}`}
                </legend>
                <label>
                  Choice key
                  <input
                    required
                    pattern="[A-Z][A-Z0-9_]{0,49}"
                    value={choice.key}
                    disabled={locked}
                    onChange={(e) => {
                      const old = choice.key,
                        next = e.target.value.toUpperCase();
                      editNode(index, {
                        choices: node.choices.map((c, i) => (i === ci ? { ...c, key: next } : c)),
                      });
                      setGraph((g) => ({
                        ...g,
                        transitions: g.transitions.map((t) =>
                          t.from_node_key === node.id && t.choice_key === old
                            ? { ...t, choice_key: next }
                            : t,
                        ),
                      }));
                    }}
                  />
                </label>
                <label>
                  Choice label
                  <input
                    required
                    maxLength={100}
                    disabled={locked}
                    value={choice.label}
                    onChange={(e) =>
                      editNode(index, {
                        choices: node.choices.map((c, i) =>
                          i === ci ? { ...c, label: e.target.value } : c,
                        ),
                      })
                    }
                  />
                </label>
                {!locked && (
                  <label>
                    Choice description
                    <textarea
                      maxLength={1000}
                      value={choice.description}
                      onChange={(e) =>
                        editNode(index, {
                          choices: node.choices.map((c, i) =>
                            i === ci ? { ...c, description: e.target.value } : c,
                          ),
                        })
                      }
                    />
                  </label>
                )}
                {!locked && (
                  <label>
                    Next node
                    <select
                      value={
                        transition?.to_node_key ??
                        choice.target_node_id ??
                        graph.nodes.find((n) => n.name === choice.target_node_name)?.id ??
                        ""
                      }
                      onChange={(e) => {
                        const next = e.target.value;
                        editNode(index, {
                          choices: node.choices.map((c, i) =>
                            i === ci ? { ...c, target_node_id: null, target_node_name: null } : c,
                          ),
                        });
                        setGraph((g) => ({
                          ...g,
                          transitions: [
                            ...g.transitions.filter(
                              (t) => !(t.from_node_key === node.id && t.choice_key === choice.key),
                            ),
                            ...(next
                              ? [
                                  {
                                    from_node_key: node.id!,
                                    choice_key: choice.key,
                                    to_node_key: next,
                                    require_approval: transition?.require_approval ?? false,
                                  },
                                ]
                              : []),
                          ],
                        }));
                      }}
                    >
                      <option value="">Finish</option>
                      {transition && !graph.nodes.some((n) => n.id === transition.to_node_key) && (
                        <option value={transition.to_node_key}>
                          Missing node — choose a new target or Finish
                        </option>
                      )}
                      {graph.nodes
                        .filter((n) => n.id !== node.id)
                        .map((n) => (
                          <option key={n.id} value={n.id}>
                            {n.name}
                          </option>
                        ))}
                    </select>
                  </label>
                )}
                {transition && (
                  <label className="toggle-row">
                    <input
                      type="checkbox"
                      checked={transition.require_approval}
                      onChange={(e) =>
                        setGraph((g) => ({
                          ...g,
                          transitions: g.transitions.map((t) =>
                            t === transition ? { ...t, require_approval: e.target.checked } : t,
                          ),
                        }))
                      }
                    />{" "}
                    Human approval before this transition
                  </label>
                )}
                {!locked && (
                  <button
                    type="button"
                    className="ghost danger"
                    onClick={() => {
                      editNode(index, { choices: node.choices.filter((_, i) => i !== ci) });
                      setGraph((g) => ({
                        ...g,
                        transitions: g.transitions.filter(
                          (t) => !(t.from_node_key === node.id && t.choice_key === choice.key),
                        ),
                      }));
                    }}
                  >
                    Remove choice {choice.key}
                  </button>
                )}
              </fieldset>
            );
          })}
          <button
            type="button"
            className="ghost"
            onClick={() =>
              editNode(index, {
                choices: [...node.choices, { key: "", label: "", description: "" }],
              })
            }
          >
            Add choice to {node.name}
          </button>
          {index > 0 && (
            <button
              type="button"
              className="ghost danger"
              onClick={() =>
                setGraph((g) => ({
                  ...g,
                  nodes: g.nodes.filter((_, i) => i !== index),
                  // Incoming targets remain visible for explicit repair, but
                  // a removed source no longer has controls to edit its edges.
                  transitions: g.transitions.filter((t) => t.from_node_key !== node.id),
                }))
              }
            >
              Remove node {node.name}
            </button>
          )}
        </fieldset>
      ))}
      <button
        type="button"
        className="ghost"
        disabled={busy}
        onClick={() =>
          setGraph((g) => ({
            ...g,
            nodes: [
              ...g.nodes,
              {
                id: crypto.randomUUID(),
                name: `Node ${g.nodes.length + 1}`,
                instructions: service.instructions,
                choices: [
                  { key: "CONTINUE", label: "Continue", description: "" },
                  { key: "UNKNOWN", label: "Unknown", description: "Permanent fallback" },
                ],
              },
            ],
          }))
        }
      >
        Add node
      </button>
      {error && (
        <p role="alert" className="field-error">
          {error}
        </p>
      )}
      {saved && (
        <p role="status">New version saved. Refresh the service before making another edit.</p>
      )}
      <button type="submit" disabled={busy || saved}>
        {busy ? "Saving graph…" : "Save new graph version"}
      </button>
    </form>
  );
}
