import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Boxes,
  CheckCircle2,
  ChevronRight,
  Circle,
  Clock3,
  MoreHorizontal,
  Network,
  Plus,
  Sparkles,
  TriangleAlert,
  Workflow as WorkflowIcon,
  Zap,
} from "lucide-react";
import { api, post } from "./api";
import { useWorkspace } from "./App";
import type { DashboardData, Workflow } from "./types";
import {
  ago,
  duration,
  Empty,
  ErrorState,
  Loading,
  Status,
  useToast,
} from "./ui";

function ActivityChart({ data }: { data: DashboardData }) {
  const [selected, setSelected] = useState<number | null>(null);
  const max = Math.max(4, ...data.hours.map((h) => h.total));
  const hours = selected === null ? null : data.hours[selected];
  return (
    <div className="activity-chart">
      <div className="chart-y">
        {[
          max,
          Math.round(max * 0.75),
          Math.round(max * 0.5),
          Math.round(max * 0.25),
          0,
        ].map((v, i) => (
          <span key={i}>{v}</span>
        ))}
      </div>
      <div className="chart-plot">
        <div className="chart-grid">
          {Array.from({ length: 5 }, (_, i) => (
            <div key={i} />
          ))}
        </div>
        <div className="chart-bars">
          {data.hours.map((h, i) => (
            <button
              key={h.time}
              aria-label={`${new Date(h.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}: ${h.total} executions, ${h.failed} failed`}
              onMouseEnter={() => setSelected(i)}
              onMouseLeave={() => setSelected(null)}
              onFocus={() => setSelected(i)}
              onBlur={() => setSelected(null)}
            >
              <span
                className="bar-failure"
                style={{ height: `${(h.failed / max) * 100}%` }}
              />
              <span
                className="bar-success"
                style={{ height: `${(h.succeeded / max) * 100}%` }}
              />
              <span
                className="bar-other"
                style={{
                  height: `${(Math.max(0, h.total - h.succeeded - h.failed) / max) * 100}%`,
                }}
              />
            </button>
          ))}
        </div>
        <div className="chart-x">
          {data.hours
            .filter((_, i) => i % 4 === 0 || i === 23)
            .map((h) => (
              <span key={h.time}>
                {new Date(h.time).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  hour12: false,
                })}
              </span>
            ))}
        </div>
        {hours && (
          <div className="chart-tooltip">
            <strong>{hours.total} executions</strong>
            <span>
              {hours.succeeded} succeeded · {hours.failed} failed
            </span>
          </div>
        )}
        {data.runs_today === 0 && (
          <div className="chart-empty">
            <Activity size={24} />
            <span>Your first execution will appear here.</span>
          </div>
        )}
      </div>
    </div>
  );
}

function MiniFlow() {
  return (
    <div
      className="mini-flow"
      aria-label="Trigger, validate, route, and prepare an order"
    >
      <div className="mini-node trigger">
        <Zap size={15} />
        <span>Webhook</span>
      </div>
      <div className="mini-connector" />
      <div className="mini-node">
        <CheckCircle2 size={15} />
        <span>Validate</span>
      </div>
      <div className="mini-connector" />
      <div className="mini-node condition">
        <WorkflowIcon size={15} />
        <span>Route order</span>
      </div>
      <div className="mini-branches">
        <div>
          <span className="branch-caption">Priority</span>
          <div className="mini-node">
            <Sparkles size={13} />
            <span>VIP</span>
          </div>
        </div>
        <div>
          <span className="branch-caption">Standard</span>
          <div className="mini-node">
            <Network size={13} />
            <span>Standard</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Dashboard() {
  const { user, canEdit } = useWorkspace(),
    navigate = useNavigate(),
    toast = useToast();
  const data = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardData>("/dashboard"),
    refetchInterval: 15000,
  });
  const workflows = useQuery({
    queryKey: ["workflows"],
    queryFn: () => api<Workflow[]>("/workflows"),
  });
  const [metric, setMetric] = useState("executions");
  if (data.isPending) return <Loading />;
  if (data.isError)
    return <ErrorState error={data.error} retry={() => void data.refetch()} />;
  const d = data.data;
  async function create() {
    try {
      const w = await post<Workflow>("/workflows", {
        name: "Untitled workflow",
      });
      navigate("/workflows/" + w.id);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  return (
    <div className="page dashboard">
      <div className="page-heading">
        <div>
          <div className="greeting">Your automation workspace</div>
          <h1>Everything is connected.</h1>
          <p>
            Welcome back, {user.display_name.split(" ")[0]}. Here’s how your
            workflows are doing.
          </p>
        </div>
        {canEdit && (
          <button className="button primary" onClick={() => void create()}>
            <Plus size={16} />
            Create workflow
          </button>
        )}
      </div>
      <div className="metric-grid">
        <div className="metric">
          <div className="metric-title">
            <span>Active workflows</span>
            <Network size={16} />
          </div>
          <strong>
            {d.active_workflows}
            <span className="metric-unit">workflows</span>
          </strong>
          <p>
            <span className="metric-dot violet" />
            Ready to receive events
          </p>
        </div>
        <div className="metric">
          <div className="metric-title">
            <span>Executions</span>
            <Activity size={16} />
          </div>
          <strong>
            {d.runs_today.toLocaleString()}
            <span className="metric-unit">last 24 hours</span>
          </strong>
          <p>
            {d.queued ? (
              <>
                <Clock3 size={12} />
                {d.queued} in progress
              </>
            ) : (
              <>
                <CheckCircle2 size={12} />
                No executions waiting
              </>
            )}
          </p>
        </div>
        <div className="metric">
          <div className="metric-title">
            <span>Success rate</span>
            <CheckCircle2 size={16} />
          </div>
          <strong>
            {d.success_rate === null ? "—" : d.success_rate}
            <span className="metric-unit">
              {d.success_rate === null ? "awaiting executions" : "%"}
            </span>
          </strong>
          <p>
            <span className="metric-dot green" />
            Completed executions
          </p>
        </div>
        <div className="metric">
          <div className="metric-title">
            <span>Average duration</span>
            <Clock3 size={16} />
          </div>
          <strong>
            {d.avg_duration_ms === null
              ? "—"
              : duration(d.avg_duration_ms).split(" ")[0]}
            <span className="metric-unit">
              {d.avg_duration_ms === null
                ? "awaiting executions"
                : duration(d.avg_duration_ms).split(" ")[1]}
            </span>
          </strong>
          <p>
            <span className="metric-dot cyan" />
            p95 {duration(d.p95_duration_ms)}
          </p>
        </div>
      </div>
      <div className="dashboard-main">
        <section className="panel execution-activity">
          <div className="panel-header">
            <div>
              <h2>Execution activity</h2>
              <p>A clear picture of every run.</p>
            </div>
            <div className="segmented">
              <button
                className={metric === "executions" ? "selected" : ""}
                onClick={() => setMetric("executions")}
              >
                Executions
              </button>
              <button
                className={metric === "latency" ? "selected" : ""}
                onClick={() => setMetric("latency")}
              >
                Latency
              </button>
            </div>
          </div>
          <div className="chart-summary">
            <strong>
              {metric === "executions"
                ? d.runs_today
                : duration(d.p95_duration_ms)}
            </strong>
            <span>
              {metric === "executions"
                ? "total executions in the last 24 hours"
                : "p95 execution duration"}
            </span>
            <div className="chart-legend">
              <span>
                <i className="violet" />
                Succeeded
              </span>
              <span>
                <i className="red" />
                Failed
              </span>
            </div>
          </div>
          {metric === "executions" ? (
            <ActivityChart data={d} />
          ) : (
            <div className="latency-chart">
              <svg
                viewBox="0 0 800 170"
                role="img"
                aria-label="Hourly p95 execution latency"
              >
                <path
                  className="chart-axis"
                  d="M0 150H800 M0 100H800 M0 50H800"
                />
                <polyline
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth="2.5"
                  strokeLinejoin="round"
                  points={d.hours
                    .map(
                      (h, i) =>
                        `${(i / 23) * 800},${150 - (h.latency_ms / Math.max(1, ...d.hours.map((v) => v.latency_ms))) * 130}`,
                    )
                    .join(" ")}
                />
              </svg>
              <p>
                Hourly p95 duration ·{" "}
                {Intl.DateTimeFormat().resolvedOptions().timeZone}
              </p>
            </div>
          )}
        </section>
        <section className="panel system-panel">
          <div className="panel-header">
            <h2>System health</h2>
            <span className="health-indicator">
              <span className="live-dot" />
              Connected
            </span>
          </div>
          <div className="health-row">
            <span>
              <span className="health-icon">
                <Circle size={15} />
              </span>
              PostgreSQL
            </span>
            <strong>Healthy</strong>
          </div>
          <div className="health-row">
            <span>
              <span className="health-icon">
                <Zap size={15} />
              </span>
              Execution runtime
            </span>
            <strong>ASGI</strong>
          </div>
          <div className="health-row">
            <span>
              <span className="health-icon">
                <Boxes size={15} />
              </span>
              Queued executions
            </span>
            <strong>{d.queued}</strong>
          </div>
          <div className="health-row">
            <span>
              <span className="health-icon">
                <TriangleAlert size={15} />
              </span>
              Failed in 24h
            </span>
            <Link to="/failed" className={d.failed_runs ? "error-text" : ""}>
              {d.failed_runs}
              <ChevronRight size={13} />
            </Link>
          </div>
          <div className="system-note">
            <ShieldCheckIcon />
            <span>
              Durable execution history.
              <br />
              Credentials encrypted at rest.
            </span>
          </div>
          <Link to="/settings" className="text-link">
            View instance details
            <ArrowUpRight size={14} />
          </Link>
        </section>
      </div>
      <div className="dashboard-lower">
        <section className="panel recent-workflows">
          <div className="panel-header">
            <div>
              <h2>Your workflows</h2>
              <p>Pick up where you left off.</p>
            </div>
            <Link className="text-link" to="/workflows">
              View all
              <ArrowRight size={14} />
            </Link>
          </div>
          <div className="workflow-preview-grid">
            {workflows.data?.slice(0, 3).map((w, i) => (
              <Link
                to={"/workflows/" + w.id}
                className="workflow-preview"
                key={w.id}
              >
                <div className="workflow-preview-top">
                  <span className={`workflow-tile tile-${i % 3}`}>
                    <Network size={18} />
                  </span>
                  <Status value={w.status} tiny />
                  <MoreHorizontal size={16} />
                </div>
                <h3>{w.name}</h3>
                <p>{w.description}</p>
                <div className="preview-path">
                  <span>
                    <Zap size={12} />
                    {w.definition.nodes[0]?.type || "No trigger"}
                  </span>
                  <ArrowRight size={12} />
                  <span>{w.definition.nodes.length} nodes</span>
                </div>
                <footer>
                  <span>Edited {ago(w.updated_at)}</span>
                  <ArrowUpRight size={15} />
                </footer>
              </Link>
            ))}
            {workflows.data?.length === 0 && (
              <Empty
                title="Start with a connection"
                description="Create a workflow or choose a template."
              />
            )}
          </div>
        </section>
        <section className="quick-start">
          <span className="quick-start-icon">
            <Sparkles size={20} />
          </span>
          <h2>From event to outcome.</h2>
          <p>
            A good workflow starts with a little structure. Our templates take
            care of that.
          </p>
          <MiniFlow />
          <Link to="/templates" className="button secondary">
            Explore templates
            <ArrowUpRight size={15} />
          </Link>
        </section>
      </div>
      <section className="panel recent-runs">
        <div className="panel-header">
          <h2>Recent executions</h2>
          <Link to="/runs" className="text-link">
            Execution history
            <ArrowRight size={14} />
          </Link>
        </div>
        {d.recent_runs.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Workflow</th>
                  <th>Execution</th>
                  <th>Status</th>
                  <th>Trigger</th>
                  <th>Duration</th>
                  <th>Started</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {d.recent_runs.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link to={"/runs/" + r.id} className="table-name">
                        <span className="table-icon">
                          <Network size={15} />
                        </span>
                        {r.workflow_name}
                      </Link>
                    </td>
                    <td>
                      <code className="run-id">{r.id.slice(0, 8)}</code>
                      <span className="version-label">v{r.version_number}</span>
                    </td>
                    <td>
                      <Status value={r.status} />
                    </td>
                    <td className="capitalize">{r.trigger_type}</td>
                    <td>{duration(r.duration_ms)}</td>
                    <td className="muted">{ago(r.created_at)}</td>
                    <td>
                      <Link
                        to={"/runs/" + r.id}
                        aria-label="Inspect execution"
                        className="icon-button"
                      >
                        <ArrowUpRight size={15} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            icon={<Activity size={24} />}
            title="Every execution has a story"
            description="Run a workflow to see its timeline, output, and status here."
          />
        )}
      </section>
      <div className="page-footer">
        <span>
          <span className="live-dot" />
          Connected to your workspace
        </span>
        <span>Connect systems. Orchestrate work. See every execution.</span>
      </div>
    </div>
  );
}
function ShieldCheckIcon() {
  return <CheckCircle2 size={18} />;
}
