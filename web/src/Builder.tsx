import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useBlocker, useParams } from "react-router-dom";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
  SelectionMode,
  useReactFlow,
  type NodeProps,
  type Connection as FlowConnection,
} from "@xyflow/react";
import {
  ArrowLeft,
  ArrowRight,
  Braces,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Clock3,
  Copy,
  Database,
  Download,
  GitBranch,
  Globe,
  Grip,
  History,
  Layers,
  MoreHorizontal,
  MousePointer2,
  Network,
  Play,
  Plus,
  Redo2,
  Send,
  Settings2,
  ShieldCheck,
  Terminal,
  Trash2,
  Undo2,
  Unplug,
  X,
  Zap,
} from "lucide-react";
import { api, ApiError, download, patch, post, queryClient } from "./api";
import { useWorkspace } from "./App";
import { definitionOf, nodeKinds, useEditor, type EditorNode } from "./editor";
import type {
  Config,
  Connection,
  Definition,
  NodeRun,
  Run,
  Validation,
  Workflow,
} from "./types";
import { terminal } from "./types";
import {
  date,
  duration,
  ErrorState,
  JsonView,
  Loading,
  Modal,
  Status,
  useToast,
} from "./ui";
export const nodeIcons: Record<string, typeof Zap> = {
  manual: MousePointer2,
  webhook: Zap,
  api: Unplug,
  schedule: CalendarClock,
  validate: ShieldCheck,
  condition: GitBranch,
  transform: Braces,
  set: Layers,
  delay: Clock3,
  http: Globe,
  postgres: Database,
  callback: Send,
};
function WorkflowNode({ data, selected }: NodeProps<EditorNode>) {
  const kind = nodeKinds.find((k) => k.kind === data.kind),
    Icon = nodeIcons[data.kind] || Network;
  const branches =
    data.kind === "condition"
      ? ["true", "false"]
      : data.kind === "validate"
        ? ["valid", "invalid"]
        : ["success"];
  const subtitle =
    data.kind === "http" || data.kind === "callback"
      ? `${data.config.method || "POST"} · ${String(data.config.url || "Configure request").replace(/^https?:\/\//, "")}`
      : data.kind === "condition"
        ? `${String(data.config.operator || "").replace("_", " ")} ${data.config.right ?? ""}`
        : kind?.hint;
  return (
    <div
      className={`flow-node ${selected ? "selected" : ""} ${data.error ? "has-error" : ""} ${data.status ? "node-state-" + data.status.toLowerCase() : ""}`}
    >
      {!["manual", "webhook", "api", "schedule"].includes(data.kind) && (
        <Handle type="target" position={Position.Top} />
      )}
      <div className="flow-node-body">
        <span className={`node-icon ${kind?.color}`}>
          <Icon size={20} />
        </span>
        <div>
          <strong>{data.label || kind?.name}</strong>
          <span>{subtitle}</span>
        </div>
        <MoreHorizontal size={16} />
      </div>
      <div className="flow-node-footer">
        <span>{kind?.name || data.kind}</span>
        {data.status ? (
          <Status value={data.status} tiny />
        ) : data.error ? (
          <span className="error-text">Needs attention</span>
        ) : (
          <span className="node-ready">
            <span />
            Draft
          </span>
        )}
      </div>
      {branches.map((branch, i) => (
        <div key={branch}>
          <Handle
            type="source"
            id={branch}
            position={Position.Bottom}
            style={{
              left: `${((i + 1) / (branches.length + 1)) * 100}%`,
              background:
                branches.length > 1
                  ? i === 0
                    ? "var(--success)"
                    : "var(--warning)"
                  : "var(--accent)",
            }}
          />
          {branches.length > 1 && (
            <span
              className={`handle-label ${i === 0 ? "yes" : "no"}`}
              style={{ left: `${((i + 1) / (branches.length + 1)) * 100}%` }}
            >
              {branch}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
const nodeTypes = { workflow: WorkflowNode };
export function JsonField({
  scope,
  label,
  value,
  onChange,
  help,
  disabled = false,
}: {
  scope: string;
  label: string;
  value: unknown;
  onChange: (v: unknown) => void;
  help?: string;
  disabled?: boolean;
}) {
  const key = scope + ":" + label;
  const invalid = useEditor((s) => s.invalidFields[key]);
  const raw = invalid?.raw ?? JSON.stringify(value ?? {}, null, 2);
  const error = invalid?.error;
  return (
    <label>
      {label}
      <textarea
        className={`code-input ${error ? "invalid" : ""}`}
        value={raw}
        disabled={disabled}
        spellCheck={false}
        rows={Math.min(10, Math.max(3, raw.split("\n").length))}
        onChange={(e) => {
          try {
            const parsed = JSON.parse(e.target.value);
            onChange(parsed);
            useEditor.getState().setInvalidField(key);
          } catch (err) {
            useEditor.getState().setInvalidField(key, {
              raw: e.target.value,
              error:
                err instanceof SyntaxError
                  ? "Enter valid JSON. This field has not been saved."
                  : (err as Error).message,
            });
          }
        }}
        aria-invalid={!!error}
      />
      {error ? (
        <small className="error-text" role="alert">
          {error}
        </small>
      ) : (
        help && <small>{help}</small>
      )}
    </label>
  );
}
function Inspector({
  node,
  editable,
  connections,
  workflow,
  runNode,
  onClose,
  onHook,
  onConnect,
}: {
  node?: EditorNode;
  editable: boolean;
  connections: Connection[];
  workflow: Workflow;
  runNode?: NodeRun;
  onClose: () => void;
  onHook: () => void;
  onConnect: (connection: FlowConnection) => void;
}) {
  const availableNodes = useEditor((s) => s.nodes);
  const update = useEditor((s) => s.updateNode),
    duplicate = useEditor((s) => s.duplicate),
    deleteNode = useEditor((s) => s.deleteNode);
  const config = node?.data.config || {},
    kind = node?.data.kind || "",
    Icon = nodeIcons[kind] || Network;
  const set = (key: string, value: unknown) => {
    if (node && editable)
      update(node.id, { config: { ...config, [key]: value } });
  };
  const retry = (config.retry as Config) || {};
  return (
    <aside className="inspector">
      <div className="inspector-heading">
        <span>{node ? "Node settings" : "Workflow overview"}</span>
        <button
          className="icon-button"
          onClick={onClose}
          title="Close inspector"
          aria-label="Close inspector"
        >
          <X size={16} />
        </button>
      </div>
      {node ? (
        <>
          <div className="inspector-node-title">
            <span
              className={`node-icon ${nodeKinds.find((n) => n.kind === kind)?.color}`}
            >
              <Icon size={23} />
            </span>
            <div>
              <h2>{nodeKinds.find((n) => n.kind === kind)?.name}</h2>
              <span>{node.data.label}</span>
            </div>
          </div>
          <div className="inspector-scroll">
            <div className="inspector-section">
              <h3>Configuration</h3>
              <label>
                Node name
                <input
                  value={node.data.label}
                  maxLength={120}
                  disabled={!editable}
                  onChange={(e) => update(node.id, { label: e.target.value })}
                />
              </label>
              <label>
                Reference name
                <input
                  value={node.data.alias}
                  placeholder="e.g. inventory"
                  disabled={!editable}
                  onChange={(e) => update(node.id, { alias: e.target.value })}
                />
                <small>Use this name in expressions: nodes.name.output</small>
              </label>
              {node.data.error && (
                <div className="inline-error">{node.data.error}</div>
              )}
              {kind === "manual" && (
                <div className="info-note">
                  Starts with the sample JSON you provide in a test or manual
                  run.
                </div>
              )}
              {kind === "api" && (
                <div className="info-note">
                  Use a scoped API key to call POST /api/v1/workflows/
                  {workflow.id}/run.
                </div>
              )}
              {kind === "webhook" && (
                <>
                  <div className="info-note">
                    Receive POST requests with JSON. The endpoint URL contains a
                    secret token and is shown only once.
                  </div>
                  {editable && (
                    <button
                      className="button secondary full-width"
                      onClick={onHook}
                    >
                      <Unplug size={15} />
                      {workflow.webhook_enabled
                        ? "Rotate webhook URL"
                        : "Generate webhook URL"}
                    </button>
                  )}
                </>
              )}
              {kind === "schedule" && (
                <>
                  <label>
                    Cron expression
                    <input
                      value={String(config.cron || "")}
                      placeholder="0 9 * * *"
                      disabled={!editable}
                      onChange={(e) => set("cron", e.target.value)}
                    />
                  </label>
                  <label>
                    Timezone
                    <input
                      value={String(config.timezone || "")}
                      disabled={!editable}
                      onChange={(e) => set("timezone", e.target.value)}
                    />
                  </label>
                  <div className="info-note">
                    Publish, then add the schedule on the Schedules page. Timing
                    depends on your scheduler invocation frequency.
                  </div>
                </>
              )}
              {["http", "callback"].includes(kind) && (
                <>
                  <div className="form-row">
                    <label>
                      Method
                      <select
                        value={String(
                          config.method ||
                            (kind === "callback" ? "POST" : "GET"),
                        )}
                        disabled={!editable}
                        onChange={(e) => set("method", e.target.value)}
                      >
                        {["GET", "POST", "PUT", "PATCH", "DELETE"].map((v) => (
                          <option key={v}>{v}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Timeout (seconds)
                      <input
                        type="number"
                        min="1"
                        max="120"
                        value={Number(config.timeout || 30)}
                        disabled={!editable}
                        onChange={(e) => set("timeout", Number(e.target.value))}
                      />
                    </label>
                  </div>
                  <label>
                    Request URL
                    <input
                      value={String(config.url || "")}
                      placeholder="https://api.example.com/orders"
                      disabled={!editable}
                      onChange={(e) => set("url", e.target.value)}
                    />
                  </label>
                  <label>
                    Authentication
                    <select
                      value={String(config.connection_id || "")}
                      disabled={!editable}
                      onChange={(e) => set("connection_id", e.target.value)}
                    >
                      <option value="">No authentication</option>
                      {connections
                        .filter((c) => c.enabled && c.type !== "postgres")
                        .map((c) => (
                          <option value={c.id} key={c.id}>
                            {c.name}
                          </option>
                        ))}
                    </select>
                    <small>
                      Credentials stay in your encrypted connection.
                    </small>
                  </label>
                  <JsonField
                    scope={node.id}
                    label="Headers"
                    value={config.headers || {}}
                    disabled={!editable}
                    onChange={(v) => {
                      if (!v || Array.isArray(v) || typeof v !== "object")
                        throw new Error("Headers must be a JSON object.");
                      if (
                        Object.keys(v).some((k) =>
                          /authorization|cookie|token|api[-_]?key|secret|password/i.test(
                            k,
                          ),
                        )
                      )
                        throw new Error(
                          "Store authentication headers in an encrypted connection.",
                        );
                      set("headers", v);
                    }}
                  />
                  <JsonField
                    scope={node.id}
                    label="Query parameters"
                    value={config.query || {}}
                    disabled={!editable}
                    onChange={(v) => set("query", v)}
                  />
                  <JsonField
                    scope={node.id}
                    label="JSON body"
                    value={config.body ?? {}}
                    disabled={!editable}
                    onChange={(v) => set("body", v)}
                    help='Use "{{ trigger.body }}" for the full payload.'
                  />
                  <label>
                    Response extraction
                    <input
                      value={String(config.extract || "")}
                      placeholder="e.g. body.customer.id"
                      disabled={!editable}
                      onChange={(e) => set("extract", e.target.value)}
                    />
                  </label>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={Boolean(config.follow_redirects)}
                      disabled={!editable}
                      onChange={(e) =>
                        set("follow_redirects", e.target.checked)
                      }
                    />
                    Follow redirects (up to 5)
                  </label>
                </>
              )}
              {kind === "postgres" && (
                <>
                  <label>
                    Database connection
                    <select
                      value={String(config.connection_id || "")}
                      disabled={!editable}
                      onChange={(e) => set("connection_id", e.target.value)}
                    >
                      <option value="">Select a connection</option>
                      {connections
                        .filter((c) => c.enabled && c.type === "postgres")
                        .map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Query mode
                    <select
                      value={String(config.mode || "read")}
                      disabled={!editable}
                      onChange={(e) => set("mode", e.target.value)}
                    >
                      <option value="read">Read only</option>
                      <option value="write">Write (requires permission)</option>
                    </select>
                  </label>
                  <label>
                    Parameterized query
                    <textarea
                      className="code-input"
                      rows={5}
                      value={String(config.query || "")}
                      disabled={!editable}
                      onChange={(e) => set("query", e.target.value)}
                      spellCheck={false}
                    />
                    <small>
                      Use %(name)s parameters. Do not put expressions in SQL.
                    </small>
                  </label>
                  <JsonField
                    scope={node.id}
                    label="Parameters"
                    value={config.parameters || {}}
                    disabled={!editable}
                    onChange={(v) => set("parameters", v)}
                  />
                </>
              )}
              {["transform", "set"].includes(kind) && (
                <JsonField
                  scope={node.id}
                  label="Field mapping"
                  value={config.mapping || {}}
                  disabled={!editable}
                  onChange={(v) => set("mapping", v)}
                  help='Example: { "email": "{{ trigger.body.customer.email }}" }'
                />
              )}
              {kind === "validate" && (
                <>
                  <label>
                    Input expression
                    <input
                      value={String(config.input || "{{ trigger.body }}")}
                      disabled={!editable}
                      onChange={(e) => set("input", e.target.value)}
                    />
                  </label>
                  <JsonField
                    scope={node.id}
                    label="JSON Schema"
                    value={config.schema || { type: "object" }}
                    disabled={!editable}
                    onChange={(v) => set("schema", v)}
                    help="Self-contained JSON Schema. External references are disabled."
                  />
                </>
              )}
              {kind === "condition" && (
                <>
                  <label>
                    Left value
                    <input
                      value={String(config.left || "")}
                      disabled={!editable}
                      onChange={(e) => set("left", e.target.value)}
                    />
                  </label>
                  <label>
                    Operator
                    <select
                      value={String(config.operator || "equals")}
                      disabled={!editable}
                      onChange={(e) => set("operator", e.target.value)}
                    >
                      {[
                        ["equals", "Equals"],
                        ["not_equals", "Does not equal"],
                        ["contains", "Contains"],
                        ["exists", "Exists"],
                        ["greater", "Greater than"],
                        ["less", "Less than"],
                        ["regex", "Matches regex"],
                      ].map(([v, l]) => (
                        <option key={v} value={v}>
                          {l}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Right value
                    <input
                      value={String(config.right ?? "")}
                      disabled={!editable}
                      onChange={(e) => {
                        const v = e.target.value;
                        set(
                          "right",
                          /^(?:-?\d+(?:\.\d+)?)$/.test(v)
                            ? Number(v)
                            : v === "true"
                              ? true
                              : v === "false"
                                ? false
                                : v,
                        );
                      }}
                    />
                  </label>
                  <details>
                    <summary>AND / OR rules</summary>
                    <JsonField
                      scope={node.id}
                      label="Condition configuration"
                      value={config}
                      disabled={!editable}
                      onChange={(v) => {
                        if (v && typeof v === "object")
                          update(node.id, { config: v as Config });
                      }}
                      help='Use { "mode": "AND", "rules": [...] } for a group.'
                    />
                  </details>
                </>
              )}
              {kind === "delay" && (
                <label>
                  Delay (seconds)
                  <input
                    type="number"
                    min="0"
                    max="86400"
                    value={Number(config.seconds ?? 5)}
                    disabled={!editable}
                    onChange={(e) => set("seconds", Number(e.target.value))}
                  />
                  <small>
                    The delay is persisted. No worker sleeps; a later invocation
                    resumes it.
                  </small>
                </label>
              )}
            </div>
            {["http", "callback", "postgres"].includes(kind) && (
              <div className="inspector-section">
                <h3>
                  Retry policy<span className="muted">Bounded retries</span>
                </h3>
                <div className="form-row">
                  <label>
                    Max attempts
                    <input
                      type="number"
                      min="1"
                      max="10"
                      value={Number(retry.max_attempts || 3)}
                      disabled={!editable}
                      onChange={(e) =>
                        set("retry", {
                          ...retry,
                          max_attempts: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                  <label>
                    Initial delay (s)
                    <input
                      type="number"
                      min="0.1"
                      max="120"
                      step="0.1"
                      value={Number(retry.initial_delay || 2)}
                      disabled={!editable}
                      onChange={(e) =>
                        set("retry", {
                          ...retry,
                          initial_delay: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                </div>
                <div className="form-row">
                  <label>
                    Backoff multiplier
                    <input
                      type="number"
                      min="1"
                      max="10"
                      value={Number(retry.multiplier || 2)}
                      disabled={!editable}
                      onChange={(e) =>
                        set("retry", {
                          ...retry,
                          multiplier: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                  <label>
                    Maximum delay (s)
                    <input
                      type="number"
                      min="1"
                      max="3600"
                      value={Number(retry.max_delay || 120)}
                      disabled={!editable}
                      onChange={(e) =>
                        set("retry", {
                          ...retry,
                          max_delay: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                </div>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={retry.jitter !== false}
                    disabled={!editable}
                    onChange={(e) =>
                      set("retry", { ...retry, jitter: e.target.checked })
                    }
                  />
                  Add jitter to backoff
                </label>
                <small>
                  Connection errors, timeouts, HTTP 429 and 5xx are eligible.
                </small>
              </div>
            )}
            {runNode && (
              <div className="inspector-section">
                <h3>
                  Latest execution
                  <Status value={runNode.status} tiny />
                </h3>
                <dl className="compact-details">
                  <dt>Attempts</dt>
                  <dd>{runNode.attempt}</dd>
                  <dt>Duration</dt>
                  <dd>{duration(runNode.duration_ms)}</dd>
                  <dt>Queue</dt>
                  <dd>{runNode.queue}</dd>
                </dl>
                {runNode.error && (
                  <div className="inline-error">{runNode.error}</div>
                )}
                <details>
                  <summary>Input</summary>
                  <JsonView value={runNode.input_data} />
                </details>
                <details open>
                  <summary>Output</summary>
                  <JsonView value={runNode.output_data} />
                </details>
              </div>
            )}
            {editable && (
              <div className="inspector-section">
                <h3>Connect to the next step</h3>
                <form
                  key={node.id}
                  onSubmit={(e) => {
                    e.preventDefault();
                    const values = new FormData(e.currentTarget);
                    onConnect({
                      source: node.id,
                      target: String(values.get("target")),
                      sourceHandle: String(values.get("output")),
                      targetHandle: null,
                    });
                  }}
                >
                  <label>
                    Output handle
                    <select name="output">
                      {(kind === "condition"
                        ? ["true", "false"]
                        : kind === "validate"
                          ? ["valid", "invalid"]
                          : ["success"]
                      ).map((handle) => (
                        <option key={handle}>{handle}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Next node
                    <select name="target" required>
                      <option value="">Choose a node</option>
                      {availableNodes
                        .filter(
                          (n) =>
                            n.id !== node.id &&
                            !["manual", "webhook", "schedule", "api"].includes(
                              n.data.kind,
                            ),
                        )
                        .map((n) => (
                          <option key={n.id} value={n.id}>
                            {n.data.label}
                          </option>
                        ))}
                    </select>
                  </label>
                  <button
                    className="button secondary full-width"
                    type="submit"
                    style={{ marginTop: 15 }}
                  >
                    <Plus size={13} />
                    Connect nodes
                  </button>
                </form>
              </div>
            )}
            <div className="inspector-section expression-help">
              <Braces size={16} />
              <div>
                <strong>Connect data with expressions</strong>
                <code>{"{{ trigger.body.customer.email }}"}</code>
                <small>
                  Typed values are preserved. No scripts or raw code.
                </small>
              </div>
            </div>
          </div>
          {editable && (
            <div className="inspector-footer">
              <button
                className="button secondary"
                onClick={() => duplicate(node.id)}
              >
                <Copy size={14} />
                Duplicate
              </button>
              <button
                className="icon-button danger-hover"
                onClick={() => deleteNode(node.id)}
                title="Delete node"
                aria-label="Delete node"
              >
                <Trash2 size={16} />
              </button>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="inspector-node-title">
            <span className="node-icon violet">
              <Network size={24} />
            </span>
            <div>
              <h2>{workflow.name}</h2>
              <span>One trigger. A clear path forward.</span>
            </div>
          </div>
          <div className="inspector-scroll">
            <div className="inspector-section">
              <h3>About this workflow</h3>
              <p>
                {workflow.description ||
                  "Connect a trigger to your processing and action nodes."}
              </p>
              <dl className="compact-details">
                <dt>State</dt>
                <dd>
                  <Status value={workflow.status} tiny />
                </dd>
                <dt>Draft revision</dt>
                <dd>{workflow.revision}</dd>
                <dt>Execution model</dt>
                <dd>At least once</dd>
                <dt>Published</dt>
                <dd>
                  {workflow.active_version_id ? "Immutable version" : "Not yet"}
                </dd>
              </dl>
            </div>
            <div className="inspector-section">
              <h3>Start with a node</h3>
              <p>
                Select any node to configure its fields, credentials, and retry
                policy.
              </p>
              <div className="info-note">
                Connect the handles to define the flow. Branch merges wait for
                all parents and accept the selected successful path.
              </div>
            </div>
            <div className="inspector-section">
              <h3>A small checklist</h3>
              <div className="checklist-item">
                <CheckCircle2 size={15} />
                Configure each step
              </div>
              <div className="checklist-item">
                <CheckCircle2 size={15} />
                Validate the graph
              </div>
              <div className="checklist-item">
                <CheckCircle2 size={15} />
                Test with a real sample
              </div>
              <div className="checklist-item">
                <CheckCircle2 size={15} />
                Publish when you’re ready
              </div>
            </div>
          </div>
        </>
      )}
    </aside>
  );
}
function Console({
  run,
  onClose,
  selectedId,
}: {
  run?: Run;
  onClose: () => void;
  selectedId?: string;
}) {
  const [tab, setTab] = useState("Execution");
  const node = run?.nodes?.find((n) => n.node_id === selectedId);
  return (
    <div className="run-console">
      <div className="console-heading">
        <div className="console-tabs">
          {["Execution", "Logs", "Input", "Output", "Errors"].map((v) => (
            <button
              key={v}
              className={tab === v ? "active" : ""}
              onClick={() => setTab(v)}
            >
              {v}
            </button>
          ))}
        </div>
        <div>
          {run && (
            <>
              <code>{run.id.slice(0, 8)}</code>
              <Status value={run.status} tiny />
              <Link className="text-link" to={"/runs/" + run.id}>
                Open execution
                <ArrowRight size={13} />
              </Link>
            </>
          )}
          <button
            className="icon-button"
            aria-label="Close execution console"
            onClick={onClose}
          >
            <ChevronDown size={18} />
          </button>
        </div>
      </div>
      <div className="console-body">
        {!run ? (
          <div className="console-empty">
            <Terminal size={18} />
            <p>Run the workflow to see every step, input, and outcome.</p>
          </div>
        ) : tab === "Execution" ? (
          <div className="console-timeline">
            {run.nodes?.map((n) => (
              <div key={n.id}>
                <Status value={n.status} tiny />
                <strong>{n.label}</strong>
                <span>{duration(n.duration_ms)}</span>
                <span>
                  {n.attempt > 1
                    ? `${n.attempt} attempts`
                    : n.attempt
                      ? "1 attempt"
                      : "Not reached"}
                </span>
              </div>
            ))}
          </div>
        ) : tab === "Logs" ? (
          <div className="console-logs">
            {run.nodes?.flatMap((n) =>
              n.attempts.map((a) => (
                <div key={a.id}>
                  <time>{date(a.created_at)}</time>
                  <Status value={a.status} tiny />
                  <span>
                    {n.label} · attempt {a.number}
                  </span>
                  <span>
                    {a.error || "Completed in " + duration(a.duration_ms)}
                  </span>
                </div>
              )),
            )}
          </div>
        ) : tab === "Input" ? (
          <JsonView value={node?.input_data ?? run.trigger_payload} />
        ) : tab === "Output" ? (
          <JsonView
            value={
              node?.output_data ??
              run.nodes?.filter((n) => n.status === "SUCCEEDED").at(-1)
                ?.output_data
            }
          />
        ) : (
          <JsonView
            value={run.nodes
              ?.filter((n) => n.error)
              .map((n) => ({
                node: n.label,
                code: n.error_code,
                message: n.error,
                attempts: n.attempt,
              }))}
          />
        )}
      </div>
    </div>
  );
}
function EditorCanvas({ workflow }: { workflow: Workflow }) {
  const { canEdit } = useWorkspace(),
    toast = useToast(),
    flow = useReactFlow<EditorNode>();
  const state = useEditor(),
    [palette, setPalette] = useState(false),
    [inspector, setInspector] = useState(
      () => window.matchMedia("(min-width: 1001px)").matches,
    ),
    [consoleOpen, setConsoleOpen] = useState(false);
  const invalid = Object.keys(state.invalidFields).length > 0;
  const [validation, setValidation] = useState<Validation | null>(null),
    [saveStatus, setSaveStatus] = useState("Saved"),
    [runDialog, setRunDialog] = useState(false),
    [payload, setPayload] = useState(
      '{\n  "order_id": "ORD-2041",\n  "total": 749,\n  "customer": { "email": "customer@example.com" }\n}',
    ),
    [runId, setRunId] = useState(""),
    [busy, setBusy] = useState(""),
    [versionsOpen, setVersionsOpen] = useState(false),
    [viewVersion, setViewVersion] = useState<number | null>(null),
    [hookDialog, setHookDialog] = useState(false),
    [hookUrl, setHookUrl] = useState("");
  const [currentWorkflow, setCurrentWorkflow] = useState(workflow),
    [conflict, setConflict] = useState(false),
    [name, setName] = useState(workflow.name);
  const revision = useRef(workflow.revision),
    savedGeneration = useRef(0),
    saving = useRef(false),
    initialized = useRef(false),
    viewRef = useRef(viewVersion),
    latestName = useRef(name),
    nameDirty = useRef(false);
  viewRef.current = viewVersion;
  latestName.current = name;
  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: () => api<Connection[]>("/connections"),
  });
  const versions = useQuery({
    queryKey: ["versions", workflow.id],
    queryFn: () =>
      api<
        {
          id: string;
          number: number;
          definition: Definition;
          created_at: string;
          is_test: boolean;
        }[]
      >("/workflows/" + workflow.id + "/versions"),
    enabled: versionsOpen,
  });
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api<Run>("/workflow-runs/" + runId),
    enabled: !!runId,
    refetchInterval: (q) =>
      q.state.data && terminal(q.state.data.status) ? false : 2000,
  });
  const editable = canEdit && viewVersion === null;
  const hasChanges = () =>
    editable &&
    (Object.keys(useEditor.getState().invalidFields).length > 0 ||
      useEditor.getState().generation !== savedGeneration.current ||
      nameDirty.current);
  const dirty = hasChanges();
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      currentLocation.pathname !== nextLocation.pathname && hasChanges(),
  );
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("oxybridge:draft-state", { detail: dirty }),
    );
  }, [dirty]);
  useEffect(
    () => () => {
      window.dispatchEvent(
        new CustomEvent("oxybridge:draft-state", { detail: false }),
      );
    },
    [],
  );
  const selected = state.nodes.find((n) => n.selected),
    selectedId = selected?.id;
  const backupKey = "oxybridge:draft:" + workflow.id;
  useEffect(() => {
    useEditor.getState().load(workflow.definition);
    const backup = localStorage.getItem(backupKey);
    if (backup && canEdit) {
      try {
        const data = JSON.parse(backup);
        useEditor.getState().load(data.definition);
        useEditor.setState({ generation: 1 });
        if (data.name) setName(data.name);
        nameDirty.current = !!data.name && data.name !== workflow.name;
        toast(
          "Recovered unsaved local edits. Review them before publishing.",
          "info",
        );
      } catch {
        localStorage.removeItem(backupKey);
      }
    }
    initialized.current = true;
    return () => {
      initialized.current = false;
    };
  }, [
    workflow.id,
    backupKey,
    canEdit,
    workflow.definition,
    workflow.name,
    toast,
  ]);
  const save = useCallback(async () => {
    const editor = useEditor.getState();
    if (Object.keys(editor.invalidFields).length)
      throw new Error(
        "Fix the unfinished JSON fields before saving or publishing.",
      );
    if (
      !canEdit ||
      viewRef.current !== null ||
      conflict ||
      saving.current ||
      (editor.generation === savedGeneration.current && !nameDirty.current)
    )
      return;
    saving.current = true;
    setSaveStatus("Saving…");
    const generation = editor.generation,
      savedName = latestName.current;
    try {
      const result = await patch<Workflow>("/workflows/" + workflow.id, {
        expected_revision: revision.current,
        definition: definitionOf(editor),
        name: savedName,
      });
      revision.current = result.revision;
      savedGeneration.current = generation;
      nameDirty.current = latestName.current !== savedName;
      setCurrentWorkflow(result);
      setSaveStatus("Saved");
      if (useEditor.getState().generation === generation && !nameDirty.current)
        localStorage.removeItem(backupKey);
      void queryClient.invalidateQueries({ queryKey: ["workflows"] });
    } catch (e) {
      setSaveStatus("Save failed");
      if (e instanceof ApiError && e.status === 409) setConflict(true);
      toast((e as Error).message, "error");
      throw e;
    } finally {
      saving.current = false;
    }
  }, [workflow.id, canEdit, conflict, backupKey, toast]);
  useEffect(() => {
    if (invalid) {
      setSaveStatus("Unfinished JSON");
      setValidation(null);
    }
    if (
      !initialized.current ||
      !editable ||
      (state.generation === savedGeneration.current && !nameDirty.current)
    )
      return;
    setSaveStatus(invalid ? "Unfinished JSON" : "Unsaved changes");
    setValidation(null);
    try {
      localStorage.setItem(
        backupKey,
        JSON.stringify({
          definition: definitionOf(useEditor.getState()),
          name,
          revision: revision.current,
        }),
      );
    } catch {
      toast(
        "Local recovery storage is full. Keep this page open until changes save.",
        "error",
      );
    }
    if (invalid) return;
    let timeout: number;
    let cancelled = false;
    const attempt = () => {
      if (cancelled) return;
      if (saving.current) {
        timeout = window.setTimeout(attempt, 300);
        return;
      }
      void save().catch(() => {});
    };
    timeout = window.setTimeout(attempt, 750);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [
    state.generation,
    invalid,
    name,
    editable,
    save,
    backupKey,
    state.nodes,
    state.edges,
    toast,
  ]);
  useEffect(() => {
    const beforeUnload = (e: BeforeUnloadEvent) => {
      if (
        useEditor.getState().generation !== savedGeneration.current ||
        nameDirty.current ||
        Object.keys(useEditor.getState().invalidFields).length > 0
      ) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (
        !editable ||
        (e.target as HTMLElement).closest(
          "input, textarea, select, [contenteditable]",
        )
      )
        return;
      if (e.metaKey || e.ctrlKey) {
        if (e.key.toLowerCase() === "z") {
          e.preventDefault();
          if (e.shiftKey) useEditor.getState().redo();
          else useEditor.getState().undo();
        }
        if (e.key.toLowerCase() === "c") {
          e.preventDefault();
          useEditor.getState().copy();
          toast("Selected nodes copied.", "info");
        }
        if (e.key.toLowerCase() === "v") {
          e.preventDefault();
          useEditor.getState().paste();
        }
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [editable, toast]);
  useEffect(() => {
    if (!runId || terminal(run.data?.status || "") || !canEdit) return;
    let stopped = false,
      active = false;
    const tick = async () => {
      if (active || stopped) return;
      active = true;
      try {
        const data = await post<Run>("/workflow-runs/" + runId + "/advance");
        if (!stopped) queryClient.setQueryData(["run", runId], data);
      } catch {
        /* Polling still displays durable status when an advance request fails. */
      } finally {
        active = false;
      }
    };
    const timer = window.setInterval(() => void tick(), 2500);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [runId, run.data?.status, canEdit]);
  function addNode(
    kind: string,
    position?: {
      x: number;
      y: number;
    },
  ) {
    const entry = nodeKinds.find((n) => n.kind === kind);
    if (!entry || !editable) return;
    const parent = selected || state.nodes.at(-1);
    useEditor.getState().add({
      id: crypto.randomUUID(),
      type: kind,
      label: entry.name,
      position:
        position ||
        (parent
          ? { x: parent.position.x, y: parent.position.y + 160 }
          : flow.screenToFlowPosition({
              x: window.innerWidth / 2,
              y: window.innerHeight / 2,
            })),
      config: structuredClone(entry.config),
    });
    setPalette(false);
    setInspector(true);
  }
  function connect(connection: FlowConnection) {
    if (!editable || connection.source === connection.target) return;
    const descendants = new Set<string>(),
      stack = [connection.target];
    while (stack.length) {
      const id = stack.pop()!;
      if (descendants.has(id)) continue;
      descendants.add(id);
      stack.push(
        ...state.edges.filter((e) => e.source === id).map((e) => e.target),
      );
    }
    if (descendants.has(connection.source)) {
      toast("Cycles are not supported. Connect a downstream node.", "error");
      return;
    }
    if (
      state.edges.some(
        (e) =>
          e.source === connection.source &&
          e.target === connection.target &&
          e.sourceHandle === connection.sourceHandle,
      )
    )
      return;
    state.connect({
      id: crypto.randomUUID(),
      ...connection,
      type: "smoothstep",
    });
  }
  async function perform(action: "validate" | "publish" | "run") {
    setBusy(action);
    try {
      await save();
      if (
        saving.current ||
        conflict ||
        useEditor.getState().generation !== savedGeneration.current ||
        nameDirty.current
      )
        throw new Error(
          "Wait until all draft changes are saved, then try again.",
        );
      const result = await post<Validation>(
        "/workflows/" + workflow.id + "/validate",
      );
      setValidation(result);
      if (!result.valid) {
        toast(
          `${result.errors.length} configuration ${result.errors.length === 1 ? "issue needs" : "issues need"} attention.`,
          "error",
        );
        return;
      }
      if (action === "validate")
        toast("Workflow is valid. All nodes are connected and configured.");
      if (action === "publish") {
        const published = await post<{
          workflow: Workflow;
          version: {
            number: number;
          };
        }>("/workflows/" + workflow.id + "/publish");
        setCurrentWorkflow(published.workflow);
        void queryClient.invalidateQueries({ queryKey: ["workflows"] });
        void queryClient.invalidateQueries({
          queryKey: ["versions", workflow.id],
        });
        toast("Published version " + published.version.number + ".");
      }
      if (action === "run") setRunDialog(true);
    } catch (e) {
      if (e instanceof ApiError && e.errors)
        setValidation({ valid: false, errors: e.errors, warnings: [] });
      if (!(e instanceof ApiError && e.code === "REVISION_CONFLICT"))
        toast((e as Error).message, "error");
    } finally {
      setBusy("");
    }
  }
  async function startRun() {
    setBusy("start");
    try {
      const body = JSON.parse(payload);
      if (!body || Array.isArray(body) || typeof body !== "object")
        throw new Error("Sample input must be a JSON object.");
      const result = await post<{
        run_id: string;
      }>("/workflows/" + workflow.id + "/run", { payload: body, test: true });
      setRunId(result.run_id);
      setRunDialog(false);
      setConsoleOpen(true);
      toast("Test execution started.");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy("");
    }
  }
  const displayNodes = state.nodes.map((n) => ({
    ...n,
    ariaLabel: n.data.label,
    data: {
      ...n.data,
      status: run.data?.nodes?.find((r) => r.node_id === n.id)?.status,
      error: Object.keys(state.invalidFields).some((key) =>
        key.startsWith(n.id + ":"),
      )
        ? "Unfinished JSON"
        : validation?.errors.find((e) => e.node_id === n.id)?.message,
    },
  }));
  const displayEdges = state.edges.map((e) => ({
    ...e,
    label: ["true", "false", "valid", "invalid"].includes(e.sourceHandle || "")
      ? e.sourceHandle
      : undefined,
    style: {
      stroke:
        e.sourceHandle === "false" || e.sourceHandle === "invalid"
          ? "var(--warning)"
          : e.sourceHandle === "true" || e.sourceHandle === "valid"
            ? "var(--success)"
            : "var(--edge)",
    },
    labelStyle: { fill: "var(--muted)", fontSize: 11 },
    labelBgStyle: { fill: "var(--surface)" },
    labelBgPadding: [7, 4] as [number, number],
    labelBgBorderRadius: 5,
  }));
  return (
    <div className="builder">
      <header className="builder-header">
        <div className="builder-title">
          <Link
            to="/workflows"
            className="icon-button"
            aria-label="Back to workflows"
          >
            <ArrowLeft size={17} />
          </Link>
          <span className="workflow-tile">
            <Network size={17} />
          </span>
          <div>
            <input
              aria-label="Workflow name"
              value={name}
              maxLength={120}
              disabled={!editable}
              onChange={(e) => {
                setName(e.target.value);
                nameDirty.current = true;
              }}
            />
            <div>
              <Status value={currentWorkflow.status} tiny />
              <span
                className={`save-state ${saveStatus === "Save failed" ? "error-text" : ""}`}
              >
                <span
                  className={
                    saveStatus === "Saved" ? "live-dot" : "pending-dot"
                  }
                />
                {viewVersion !== null
                  ? "Viewing version " + viewVersion
                  : saveStatus}
              </span>
            </div>
          </div>
        </div>
        <div className="builder-actions">
          <button
            className="button ghost"
            onClick={() => setVersionsOpen(true)}
            title="Version history"
            aria-label="Version history"
          >
            <History size={15} />
            <span>Versions</span>
          </button>
          <button
            className="button secondary"
            onClick={() => void perform("validate")}
            aria-label="Validate"
            title="Validate"
            disabled={!editable || !!busy || invalid}
          >
            <CheckCircle2 size={15} />
            <span>Validate</span>
          </button>
          <button
            className="button secondary"
            onClick={() => void perform("run")}
            aria-label="Test run"
            title="Test run"
            disabled={!editable || !!busy || invalid}
          >
            <Play size={15} />
            <span>Test run</span>
          </button>
          <button
            className="button primary"
            onClick={() => void perform("publish")}
            aria-label={busy === "publish" ? "Publishing" : "Publish"}
            title="Publish"
            disabled={!editable || !!busy || invalid}
          >
            <Send size={15} />
            <span>{busy === "publish" ? "Publishing…" : "Publish"}</span>
          </button>
        </div>
      </header>
      {viewVersion !== null && (
        <div className="version-banner">
          Published versions are immutable. Viewing version {viewVersion}.
          <button
            className="text-button"
            onClick={() => {
              state.load(currentWorkflow.definition);
              savedGeneration.current = 0;
              setViewVersion(null);
              setRunId("");
            }}
          >
            Back to draft
          </button>
        </div>
      )}
      <div className="builder-workspace">
        <div className="canvas-and-console">
          <div className="flow-canvas">
            <ReactFlow<EditorNode>
              nodes={displayNodes}
              edges={displayEdges}
              nodeTypes={nodeTypes}
              onNodesChange={(changes) => {
                if (editable) state.changeNodes(changes);
                else
                  state.changeNodes(
                    changes.filter(
                      (c) => c.type === "select" || c.type === "dimensions",
                    ),
                  );
              }}
              onEdgesChange={editable ? state.changeEdges : undefined}
              onConnect={connect}
              onNodeDragStart={() => editable && state.checkpoint()}
              onNodeClick={() => setInspector(true)}
              onPaneClick={() => {}}
              nodesDraggable={editable}
              nodesConnectable={editable}
              deleteKeyCode={editable ? ["Backspace", "Delete"] : null}
              selectionMode={SelectionMode.Partial}
              selectionOnDrag
              panOnScroll
              fitView
              fitViewOptions={{ padding: 0.23, maxZoom: 1 }}
              minZoom={0.15}
              maxZoom={1.5}
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
              }}
              onDrop={(e: DragEvent) => {
                e.preventDefault();
                addNode(
                  e.dataTransfer.getData("application/oxybridge-node"),
                  flow.screenToFlowPosition({ x: e.clientX, y: e.clientY }),
                );
              }}
            >
              <Background
                variant={BackgroundVariant.Dots}
                gap={22}
                size={1.2}
                color="var(--grid)"
              />
              <Controls position="bottom-left" showInteractive={false} />
              <MiniMap
                position="bottom-right"
                pannable
                zoomable
                nodeColor="var(--accent-soft)"
                maskColor="transparent"
              />
              <Panel position="top-left">
                <div className="canvas-toolbar">
                  <button
                    className="icon-button"
                    aria-label="Undo"
                    title="Undo (Ctrl Z)"
                    disabled={!editable || !state.past.length}
                    onClick={state.undo}
                  >
                    <Undo2 size={16} />
                  </button>
                  <button
                    className="icon-button"
                    aria-label="Redo"
                    title="Redo (Ctrl Shift Z)"
                    disabled={!editable || !state.future.length}
                    onClick={state.redo}
                  >
                    <Redo2 size={16} />
                  </button>
                  <i />
                  <button
                    className="toolbar-add"
                    onClick={() => setPalette((v) => !v)}
                    disabled={!editable}
                  >
                    <Plus size={15} />
                    Add node
                  </button>
                </div>
              </Panel>
              <Panel position="top-right">
                <button
                  className="button canvas-button"
                  onClick={() => setInspector((v) => !v)}
                >
                  <Settings2 size={14} />
                  Inspector
                </button>
              </Panel>
              <Panel position="bottom-center">
                <div className="canvas-hint">
                  <MousePointer2 size={12} />
                  <span>Drag to select</span>
                  <i />
                  <span>Space + drag to pan</span>
                </div>
              </Panel>
            </ReactFlow>
            {state.nodes.length === 0 && (
              <div className="canvas-empty">
                <div className="node-icon violet">
                  <Network size={30} />
                </div>
                <h2>Your workflow starts here.</h2>
                <p>
                  Add a trigger, then connect the steps
                  <br />
                  that turn an event into an outcome.
                </p>
                {editable && (
                  <button
                    className="button primary"
                    onClick={() => setPalette(true)}
                  >
                    <Plus size={16} />
                    Add your first node
                  </button>
                )}
              </div>
            )}
            {palette && (
              <div className="node-palette">
                <div className="palette-heading">
                  <h3>Add a node</h3>
                  <button
                    className="icon-button"
                    aria-label="Close node palette"
                    onClick={() => setPalette(false)}
                  >
                    <X size={15} />
                  </button>
                </div>
                <p>Click to add, or drag onto the canvas.</p>
                {["Triggers", "Logic", "Actions"].map((group) => (
                  <div key={group}>
                    <h4>{group}</h4>
                    {nodeKinds
                      .filter((n) => n.group === group)
                      .map((n) => {
                        const Icon = nodeIcons[n.kind];
                        return (
                          <button
                            key={n.kind}
                            draggable
                            onDragStart={(e) =>
                              e.dataTransfer.setData(
                                "application/oxybridge-node",
                                n.kind,
                              )
                            }
                            onClick={() => addNode(n.kind)}
                          >
                            <span className={`node-icon ${n.color}`}>
                              <Icon size={16} />
                            </span>
                            <div>
                              <strong>{n.name}</strong>
                              <span>{n.hint}</span>
                            </div>
                            <Grip size={12} />
                          </button>
                        );
                      })}
                  </div>
                ))}
              </div>
            )}
            {validation && !validation.valid && (
              <div className="validation-panel">
                <div>
                  <strong>{validation.errors.length} issues to fix</strong>
                  <button
                    className="icon-button"
                    onClick={() => setValidation(null)}
                    aria-label="Close validation errors"
                  >
                    <X size={14} />
                  </button>
                </div>
                {validation.errors.map((e, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      if (e.node_id) {
                        state.changeNodes(
                          state.nodes.map((n) => ({
                            id: n.id,
                            type: "select" as const,
                            selected: n.id === e.node_id,
                          })),
                        );
                        setInspector(true);
                        const node = state.nodes.find(
                          (n) => n.id === e.node_id,
                        );
                        if (node)
                          void flow.setCenter(
                            node.position.x + 130,
                            node.position.y + 50,
                            { zoom: 1, duration: 250 },
                          );
                      }
                    }}
                  >
                    {e.message}
                    <ChevronRight size={14} />
                  </button>
                ))}
              </div>
            )}
          </div>
          {consoleOpen ? (
            <Console
              run={run.data}
              selectedId={selectedId}
              onClose={() => setConsoleOpen(false)}
            />
          ) : (
            <button
              className="console-collapsed"
              onClick={() => setConsoleOpen(true)}
            >
              <Terminal size={15} />
              <strong>Execution console</strong>
              {run.data ? (
                <Status value={run.data.status} tiny />
              ) : (
                <span>Run your workflow to inspect the result</span>
              )}
              <ChevronUp size={16} />
            </button>
          )}
        </div>
        {inspector && (
          <Inspector
            node={
              selected
                ? displayNodes.find((n) => n.id === selected.id)
                : undefined
            }
            editable={editable}
            connections={connections.data || []}
            workflow={currentWorkflow}
            runNode={run.data?.nodes?.find((n) => n.node_id === selectedId)}
            onClose={() => setInspector(false)}
            onConnect={connect}
            onHook={() => {
              setHookUrl("");
              setHookDialog(true);
            }}
          />
        )}
      </div>
      {runDialog && (
        <Modal
          title="Test your workflow"
          wide
          onClose={() => setRunDialog(false)}
        >
          <p>
            Runs an immutable snapshot of your saved draft. Action nodes can
            make real API calls and database writes.
          </p>
          <label>
            Sample input
            <textarea
              className="code-input"
              rows={12}
              spellCheck={false}
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
            />
          </label>
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setRunDialog(false)}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={!!busy}
              onClick={() => void startRun()}
            >
              <Play size={15} />
              {busy ? "Starting…" : "Start test run"}
            </button>
          </div>
        </Modal>
      )}
      {versionsOpen && (
        <Modal title="Version history" onClose={() => setVersionsOpen(false)}>
          <p>Each execution is pinned to an immutable definition.</p>
          <div className="version-list">
            {versions.data?.map((v) => (
              <button
                key={v.id}
                onClick={async () => {
                  try {
                    await save();
                    if (
                      useEditor.getState().generation !==
                      savedGeneration.current
                    )
                      throw new Error("Wait for the draft to save first.");
                    state.load(v.definition);
                    setViewVersion(v.number);
                    setVersionsOpen(false);
                    setRunId("");
                    savedGeneration.current = 0;
                  } catch (e) {
                    toast((e as Error).message, "error");
                  }
                }}
              >
                <span>
                  <History size={17} />
                  <strong>Version {v.number}</strong>
                  {v.is_test && <span className="tag">Test snapshot</span>}
                </span>
                <span>
                  {date(v.created_at)}
                  <ChevronRight size={16} />
                </span>
              </button>
            ))}
            {versions.data?.length === 0 && (
              <p className="muted">
                Publish or test a workflow to create its first version.
              </p>
            )}
          </div>
        </Modal>
      )}
      {blocker.state === "blocked" && (
        <Modal
          title="Keep your unfinished edits?"
          onClose={() => blocker.reset()}
        >
          <p>
            {invalid
              ? "Some JSON fields are unfinished. Leaving discards that text. Valid unsaved edits remain in local recovery storage."
              : "Your latest edits have not saved yet. Wait for them to save, or leave with a local recovery copy."}
          </p>
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => blocker.reset()}
            >
              Keep editing
            </button>
            <button
              className="button primary"
              onClick={() => blocker.proceed()}
            >
              Leave editor
            </button>
          </div>
        </Modal>
      )}
      {conflict && (
        <Modal
          title="Your draft changed in another tab"
          onClose={() => setConflict(false)}
        >
          <p>
            Your local edits are preserved. Export them before loading the
            latest server draft, so nothing is lost.
          </p>
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() =>
                download(currentWorkflow.name + "-local-draft.json", {
                  format: "OxyBridge-workflow",
                  format_version: 1,
                  workflow: {
                    name,
                    definition: definitionOf(useEditor.getState()),
                  },
                })
              }
            >
              <Download size={14} />
              Export local edits
            </button>
            <button
              className="button primary"
              onClick={async () => {
                const latest = await api<Workflow>("/workflows/" + workflow.id);
                localStorage.removeItem(backupKey);
                state.load(latest.definition);
                revision.current = latest.revision;
                savedGeneration.current = 0;
                setName(latest.name);
                nameDirty.current = false;
                setCurrentWorkflow(latest);
                setConflict(false);
                setSaveStatus("Saved");
              }}
            >
              Load latest draft
            </button>
          </div>
        </Modal>
      )}
      {hookDialog && (
        <Modal
          title={
            hookUrl ? "Your webhook is ready" : "Generate a webhook endpoint"
          }
          onClose={() => setHookDialog(false)}
        >
          {hookUrl ? (
            <>
              <p>
                Copy this URL now. It includes the authentication token and will
                be shown only once.
              </p>
              <pre className="secret-once">{hookUrl}</pre>
              <button
                className="button primary"
                onClick={async () => {
                  await navigator.clipboard.writeText(hookUrl);
                  toast("Webhook URL copied.");
                }}
              >
                <Copy size={15} />
                Copy webhook URL
              </button>
            </>
          ) : (
            <>
              <p>
                {currentWorkflow.webhook_enabled
                  ? "Rotating the URL immediately invalidates the previous token."
                  : "Publish the webhook workflow before accepting events."}
              </p>
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    const secret = new FormData(e.currentTarget).get("secret");
                    const result = await post<{
                      url: string;
                    }>("/workflows/" + workflow.id + "/webhook", {
                      hmac_secret: secret || null,
                    });
                    setHookUrl(result.url);
                    setCurrentWorkflow((v) => ({
                      ...v,
                      webhook_enabled: true,
                    }));
                  } catch (e) {
                    toast((e as Error).message, "error");
                  }
                }}
              >
                <label>
                  HMAC secret (optional)
                  <input
                    type="password"
                    name="secret"
                    minLength={20}
                    autoComplete="off"
                  />
                  <small>
                    Sign timestamp + "." + request body with SHA-256. Maximum
                    replay window: 5 minutes.
                  </small>
                </label>
                <div className="modal-actions">
                  <button className="button primary">Generate endpoint</button>
                </div>
              </form>
            </>
          )}
        </Modal>
      )}
    </div>
  );
}
export function Builder() {
  const { id } = useParams();
  const workflow = useQuery({
    queryKey: ["workflow", id],
    queryFn: () => api<Workflow>("/workflows/" + id),
  });
  if (workflow.isPending) return <Loading />;
  if (workflow.isError)
    return (
      <ErrorState
        error={workflow.error}
        retry={() => void workflow.refetch()}
      />
    );
  return (
    <ReactFlowProvider>
      <EditorCanvas key={id} workflow={workflow.data} />
    </ReactFlowProvider>
  );
}
