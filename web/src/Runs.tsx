import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  Copy,
  History,
  Network,
  RotateCcw,
  Search,
  Square,
  Terminal,
} from "lucide-react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type NodeProps,
  type Node,
} from "@xyflow/react";
import { api, post, queryClient } from "./api";
import { useWorkspace } from "./App";
import { nodeIcons } from "./Builder";
import type { Run, Workflow } from "./types";
import { terminal } from "./types";
import {
  ago,
  date,
  duration,
  Empty,
  ErrorState,
  JsonView,
  Loading,
  Modal,
  Status,
  useToast,
} from "./ui";
export function useLiveRun(id: string) {
  const { canEdit, workspace } = useWorkspace();
  const query = useQuery({
    queryKey: ["run", id],
    queryFn: () => api<Run>("/workflow-runs/" + id),
    enabled: !!id,
    refetchInterval: (q) =>
      q.state.data && terminal(q.state.data.status) ? false : 1500,
  });
  useEffect(() => {
    if (!id || terminal(query.data?.status || "")) return;
    let stopped = false,
      advancing = false;
    const stream = new EventSource(
      "/api/v1/workflow-runs/" +
        id +
        "/events/stream?workspace_id=" +
        workspace.id,
    );
    stream.addEventListener("snapshot", (event) => {
      try {
        const run = JSON.parse((event as MessageEvent).data) as Run;
        queryClient.setQueryData(["run", id], run);
        if (terminal(run.status)) stream.close();
      } catch {
        /* REST polling recovers malformed or interrupted streams. */
      }
    });
    const timer = window.setInterval(async () => {
      if (!canEdit || advancing || stopped) return;
      advancing = true;
      try {
        const run = await post<Run>("/workflow-runs/" + id + "/advance");
        if (!stopped) queryClient.setQueryData(["run", id], run);
      } catch {
        /* Polling shows the durable execution even when resumption is unavailable. */
      } finally {
        advancing = false;
      }
    }, 2500);
    return () => {
      stopped = true;
      stream.close();
      window.clearInterval(timer);
    };
  }, [id, query.data?.status, canEdit, workspace.id]);
  return query;
}
export function Runs() {
  const [status, setStatus] = useState(""),
    [workflowId, setWorkflowId] = useState(""),
    [search, setSearch] = useState(""),
    [offset, setOffset] = useState(0),
    [trigger, setTrigger] = useState(""),
    [since, setSince] = useState("");
  const runs = useQuery({
    queryKey: ["runs", status, workflowId, search, offset, trigger, since],
    queryFn: () =>
      api<Run[]>(
        `/workflow-runs?status=${status}&workflow_id=${workflowId}&search=${encodeURIComponent(search)}&offset=${offset}&trigger=${trigger}&since=${since}`,
      ),
    refetchInterval: 10000,
  });
  const workflows = useQuery({
    queryKey: ["workflows"],
    queryFn: () => api<Workflow[]>("/workflows"),
  });
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="greeting">The full picture, step by step.</div>
          <h1>Executions</h1>
          <p>
            Every run has a record. Inspect the path from trigger to result.
          </p>
        </div>
        <span className="live-label">
          <span className="live-dot" />
          Updates every 10 seconds
        </span>
      </div>
      <div className="run-filters">
        <label className="search-field">
          <Search size={16} />
          <input
            aria-label="Search execution ID"
            placeholder="Search run ID…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <select
          aria-label="Filter workflow"
          value={workflowId}
          onChange={(e) => {
            setWorkflowId(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All workflows</option>
          {workflows.data?.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter execution status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All statuses</option>
          {[
            "SUCCEEDED",
            "FAILED",
            "RUNNING",
            "QUEUED",
            "CANCELLED",
            "TIMED_OUT",
          ].map((v) => (
            <option value={v} key={v}>
              {v.toLowerCase().replace("_", " ")}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter trigger"
          value={trigger}
          onChange={(e) => {
            setTrigger(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All triggers</option>
          {["manual", "test", "webhook", "api", "schedule", "recovery"].map(
            (v) => (
              <option key={v}>{v}</option>
            ),
          )}
        </select>
        <input
          aria-label="Executed since"
          type="date"
          value={since}
          onChange={(e) => {
            setSince(e.target.value);
            setOffset(0);
          }}
        />
      </div>
      <section className="panel">
        {runs.isPending ? (
          <Loading />
        ) : runs.isError ? (
          <ErrorState error={runs.error} retry={() => void runs.refetch()} />
        ) : runs.data.length === 0 ? (
          <Empty
            icon={<Activity size={26} />}
            title="No executions here yet"
            description="Run a published workflow or test a draft. Adjust your filters to see other runs."
          >
            <Link className="button secondary" to="/workflows">
              Open workflows
              <ArrowRight size={15} />
            </Link>
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Execution</th>
                  <th>Workflow</th>
                  <th>Status</th>
                  <th>Trigger</th>
                  <th>Duration</th>
                  <th>Retries</th>
                  <th>Started</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link to={"/runs/" + r.id}>
                        <code className="run-id">{r.id.slice(0, 8)}</code>
                      </Link>
                    </td>
                    <td>
                      <Link className="table-name" to={"/runs/" + r.id}>
                        {r.workflow_name}
                        <span className="version-label">
                          v{r.version_number}
                        </span>
                        {r.is_test && <span className="tag">Test</span>}
                      </Link>
                    </td>
                    <td>
                      <Status value={r.status} />
                    </td>
                    <td className="capitalize">{r.trigger_type}</td>
                    <td>{duration(r.duration_ms)}</td>
                    <td>{r.retries}</td>
                    <td className="muted" title={date(r.created_at)}>
                      {ago(r.created_at)}
                    </td>
                    <td>
                      <Link
                        to={"/runs/" + r.id}
                        className="icon-button"
                        aria-label={"Inspect execution " + r.id.slice(0, 8)}
                      >
                        <ArrowUpRight size={16} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <div className="pagination">
        <span>
          {offset
            ? `Showing runs ${offset + 1}–${offset + (runs.data?.length || 0)}`
            : `${runs.data?.length || 0} most recent executions`}
        </span>
        <div>
          <button
            className="button secondary"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous
          </button>
          <button
            className="button secondary"
            disabled={!runs.data || runs.data.length < 50}
            onClick={() => setOffset(offset + 50)}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
type ExecutionNode = Node<
  {
    label: string;
    kind: string;
    status: string;
    duration: number | null;
  },
  "execution"
>;
function ResultNode({ data }: NodeProps<ExecutionNode>) {
  const Icon = nodeIcons[data.kind] || Network;
  return (
    <div className={"execution-node node-state-" + data.status.toLowerCase()}>
      <Handle type="target" position={Position.Top} />
      <span className="node-icon">
        <Icon size={17} />
      </span>
      <strong>{data.label}</strong>
      <div>
        <Status value={data.status} tiny />
        <span>{duration(data.duration)}</span>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
const resultNodeTypes = { execution: ResultNode };
export function RunDetail() {
  const { id = "" } = useParams(),
    navigate = useNavigate(),
    toast = useToast(),
    { canEdit } = useWorkspace();
  const query = useLiveRun(id);
  const [selected, setSelected] = useState(""),
    [tab, setTab] = useState("Output"),
    [busy, setBusy] = useState(false),
    [rerunConfirm, setRerunConfirm] = useState(false),
    [view, setView] = useState("Timeline");
  if (query.isPending) return <Loading />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const run = query.data,
    selectedNode =
      run.nodes?.find((n) => n.node_id === selected) ||
      run.nodes?.find((n) => n.status === "FAILED") ||
      run.nodes?.find((n) => n.status === "RUNNING") ||
      run.nodes?.at(-1);
  async function action(kind: string) {
    setBusy(true);
    try {
      const result = await post<{
        run_id?: string;
      }>("/workflow-runs/" + id + "/" + kind);
      if (result.run_id) navigate("/runs/" + result.run_id);
      else {
        void query.refetch();
        toast("Cancellation requested. In-flight actions can still finish.");
      }
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
      setRerunConfirm(false);
    }
  }
  const graphNodes: ExecutionNode[] =
    run.definition?.nodes.map((n) => {
      const result = run.nodes?.find((r) => r.node_id === n.id);
      return {
        id: n.id,
        type: "execution",
        position: n.position,
        data: {
          label: n.label,
          kind: n.type,
          status: result?.status || "PENDING",
          duration: result?.duration_ms ?? null,
        },
        selected: selectedNode?.node_id === n.id,
      };
    }) || [];
  return (
    <div className="page execution-detail">
      <div className="detail-breadcrumb">
        <Link to="/runs">
          <ArrowLeft size={14} />
          Executions
        </Link>
        <ChevronRight size={12} />
        <code>{run.id.slice(0, 8)}</code>
      </div>
      <div className="page-heading">
        <div>
          <h1>
            {run.workflow_name}
            <Status value={run.status} />
          </h1>
          <p>
            <code>{run.id}</code>
            <button
              className="icon-button"
              title="Copy execution ID"
              aria-label="Copy execution ID"
              onClick={async () => {
                await navigator.clipboard.writeText(run.id);
                toast("Execution ID copied.");
              }}
            >
              <Copy size={13} />
            </button>
          </p>
        </div>
        {canEdit && (
          <div className="heading-actions">
            {terminal(run.status) ? (
              <button
                className="button primary"
                disabled={busy}
                onClick={() => setRerunConfirm(true)}
              >
                <RotateCcw size={15} />
                Re-run workflow
              </button>
            ) : (
              <button
                className="button secondary"
                disabled={busy || run.status === "CANCEL_REQUESTED"}
                onClick={() => void action("cancel")}
              >
                <Square size={14} />
                Cancel execution
              </button>
            )}
            <Link
              className="button secondary"
              to={"/workflows/" + run.workflow_id}
            >
              <Network size={15} />
              Open workflow
            </Link>
          </div>
        )}
      </div>
      <div className="run-summary">
        <div>
          <span>Version</span>
          <strong>
            v{run.version_number}
            {run.is_test && <span className="tag">Test snapshot</span>}
          </strong>
        </div>
        <div>
          <span>Trigger</span>
          <strong className="capitalize">{run.trigger_type}</strong>
        </div>
        <div>
          <span>Started</span>
          <strong>{date(run.started_at || run.created_at)}</strong>
        </div>
        <div>
          <span>Duration</span>
          <strong>{duration(run.duration_ms)}</strong>
        </div>
        <div>
          <span>Retries</span>
          <strong>{run.retries}</strong>
        </div>
        <div>
          <span>Queue wait</span>
          <strong>
            {run.started_at
              ? duration(
                  new Date(run.started_at).getTime() -
                    new Date(run.created_at).getTime(),
                )
              : "Waiting"}
          </strong>
        </div>
      </div>
      {run.error && (
        <div className="execution-error">
          <Terminal size={20} />
          <div>
            <strong>{run.error_code}</strong>
            <p>{run.error}</p>
          </div>
          <Link to="/failed">
            Failed work
            <ArrowRight size={14} />
          </Link>
        </div>
      )}
      {run.recovery_of && (
        <div className="info-banner">
          <History size={15} />
          Recovery execution linked to
          <Link to={"/runs/" + run.recovery_of}>
            {run.recovery_of.slice(0, 8)}
          </Link>
          . The original history is preserved.
        </div>
      )}
      <div className="execution-detail-grid">
        <section className="panel execution-path">
          <div className="panel-header">
            <h2>Execution path</h2>
            <div className="segmented">
              {["Timeline", "Graph"].map((v) => (
                <button
                  className={view === v ? "selected" : ""}
                  key={v}
                  onClick={() => setView(v)}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
          {view === "Timeline" ? (
            <div className="node-timeline">
              {run.nodes?.map((n, i) => {
                const Icon = nodeIcons[n.node_type] || Network;
                return (
                  <button
                    key={n.id}
                    className={`timeline-row ${selectedNode?.id === n.id ? "selected" : ""}`}
                    onClick={() => setSelected(n.node_id)}
                  >
                    <span className="timeline-index">{i + 1}</span>
                    <span
                      className={
                        "node-icon " +
                        (n.status === "FAILED"
                          ? "red"
                          : n.status === "SUCCEEDED"
                            ? "green"
                            : "violet")
                      }
                    >
                      <Icon size={19} />
                    </span>
                    <div>
                      <strong>{n.label}</strong>
                      <span>
                        {n.node_type} · {n.queue}
                        {n.attempt > 1 ? ` · ${n.attempt} attempts` : ""}
                      </span>
                    </div>
                    <Status value={n.status} />
                    <span className="timeline-duration">
                      {duration(n.duration_ms)}
                    </span>
                    <ChevronRight size={15} />
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="execution-graph">
              <ReactFlow<ExecutionNode>
                nodes={graphNodes}
                edges={
                  run.definition?.edges.map((e) => ({
                    id: e.id,
                    source: e.source,
                    target: e.target,
                    type: "smoothstep",
                    label: ["true", "false", "valid", "invalid"].includes(
                      e.sourceHandle || "",
                    )
                      ? e.sourceHandle
                      : undefined,
                  })) || []
                }
                nodeTypes={resultNodeTypes}
                nodesDraggable={false}
                nodesConnectable={false}
                onNodeClick={(_, n) => setSelected(n.id)}
                fitView
                fitViewOptions={{ padding: 0.2 }}
              >
                <Background gap={20} />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
          )}
          <div className="path-footer">
            <ShieldIcon />
            This run uses the immutable definition captured at execution time.
          </div>
        </section>
        <section className="panel execution-inspect">
          <div className="panel-header">
            <div>
              <h2>{selectedNode?.label || "Trigger payload"}</h2>
              <p>Select a step to inspect its data.</p>
            </div>
            {selectedNode && <Status value={selectedNode.status} tiny />}
          </div>
          <div className="inspect-tabs">
            {["Output", "Input", "Attempts"].map((v) => (
              <button
                key={v}
                className={tab === v ? "active" : ""}
                onClick={() => setTab(v)}
              >
                {v}
              </button>
            ))}
          </div>
          <div className="inspect-body">
            {tab === "Attempts" ? (
              <div className="attempt-list">
                {selectedNode?.attempts.map((a) => (
                  <div key={a.id}>
                    <div>
                      <strong>Attempt {a.number}</strong>
                      <Status value={a.status} tiny />
                    </div>
                    <p>
                      {date(a.created_at)} · {duration(a.duration_ms)}
                    </p>
                    {a.error && <p className="error-text">{a.error}</p>}
                    {a.http_status && <code>HTTP {a.http_status}</code>}
                  </div>
                ))}
                {!selectedNode?.attempts.length && (
                  <p>This node has not run.</p>
                )}
              </div>
            ) : (
              <JsonView
                value={
                  tab === "Input"
                    ? (selectedNode?.input_data ?? run.trigger_payload)
                    : selectedNode?.output_data
                }
              />
            )}
            {selectedNode?.error && (
              <div className="inline-error">
                {selectedNode.error_code}: {selectedNode.error}
              </div>
            )}
          </div>
          <footer className="inspect-footer">
            <span>
              <Check size={13} />
              Sensitive fields redacted
            </span>
            <span>{selectedNode?.worker_id || "No worker yet"}</span>
          </footer>
        </section>
      </div>
      {rerunConfirm && (
        <Modal
          title="Re-run this workflow?"
          onClose={() => setRerunConfirm(false)}
        >
          <p>
            A new execution will use the original input and version. Action
            nodes can repeat external effects; downstream idempotency support
            determines whether those effects are duplicated.
          </p>
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setRerunConfirm(false)}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={busy}
              onClick={() => void action("rerun")}
            >
              Create recovery execution
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
function ShieldIcon() {
  return <Check size={13} />;
}
