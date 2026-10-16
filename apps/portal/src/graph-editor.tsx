import { useState, type FormEvent } from "react";
import type { DecisionGraphInput, DecisionNodeInput, DecisionService } from "@openclass/sdk";
import "./workflow.css";

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
          <label>
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
                  <label>
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
