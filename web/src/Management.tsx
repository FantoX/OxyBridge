import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  Boxes,
  CalendarClock,
  Check,
  CheckCircle2,
  Copy,
  Database,
  FileClock,
  Globe,
  KeyRound,
  LockKeyhole,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Settings2,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  Unplug,
  Users,
} from "lucide-react";
import { api, patch, post, queryClient, remove } from "./api";
import { useWorkspace } from "./App";
import type { Connection, Schedule, Template, Workflow } from "./types";
import {
  ago,
  date,
  Empty,
  ErrorState,
  JsonView,
  Loading,
  Modal,
  Status,
  useToast,
} from "./ui";
function PageHeading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="greeting">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}
function useRefresh() {
  return (...keys: string[]) =>
    keys.forEach(
      (key) => void queryClient.invalidateQueries({ queryKey: [key] }),
    );
}
export function Connections() {
  const { canAdmin } = useWorkspace(),
    toast = useToast(),
    refresh = useRefresh();
  const data = useQuery({
    queryKey: ["connections"],
    queryFn: () => api<Connection[]>("/connections"),
  });
  const [dialog, setDialog] = useState<Connection | "new" | null>(null),
    [kind, setKind] = useState("bearer"),
    [search, setSearch] = useState(""),
    [busy, setBusy] = useState(false),
    [deleting, setDeleting] = useState<Connection | null>(null),
    [rotate, setRotate] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    const values = Object.fromEntries(new FormData(e.currentTarget)),
      secret: Record<string, string | number> = {};
    const edit = dialog !== null && dialog !== "new";
    try {
      if (!edit || rotate) {
        for (const key of kind === "bearer"
          ? ["token"]
          : kind === "api_key"
            ? ["token", "header"]
            : kind === "basic"
              ? ["username", "password"]
              : ["host", "database", "username", "password", "port", "sslmode"])
          secret[key] = String(values[key] || "");
        if (kind === "postgres") secret.port = Number(secret.port || 5432);
      }
      const body = {
        name: values.name,
        allow_writes: values.allowWrites === "on",
        ...(kind !== "postgres"
          ? {
              allowed_hosts: String(values.allowedHosts || "")
                .split(",")
                .map((h) => h.trim())
                .filter(Boolean),
            }
          : {}),
        ...(!edit || rotate ? { secret } : {}),
      };
      if (edit) await patch("/connections/" + dialog.id, body);
      else await post("/connections", { ...body, type: kind });
      toast(edit ? "Connection updated." : "Encrypted connection created.");
      setDialog(null);
      refresh("connections");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  function open(connection?: Connection) {
    setDialog(connection || "new");
    setKind(connection?.type || "bearer");
    setRotate(false);
  }
  const filtered =
    data.data?.filter((c) =>
      c.name.toLowerCase().includes(search.toLowerCase()),
    ) || [];
  return (
    <div className="page">
      <PageHeading
        eyebrow="A secure home for your integrations."
        title="Connections"
        description="Reusable credentials, encrypted at rest and kept out of your workflows."
      >
        {canAdmin && (
          <button className="button primary" onClick={() => open()}>
            <Plus size={16} />
            Add connection
          </button>
        )}
      </PageHeading>
      <div className="info-banner">
        <LockKeyhole size={17} />
        Secret values are never returned after saving. Rotate credentials
        without editing each workflow.
      </div>
      <div className="list-toolbar">
        <span className="muted">
          {filtered.length} connections in this workspace
        </span>
        <label className="search-field">
          <Search size={15} />
          <input
            aria-label="Search connections"
            placeholder="Search connections…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      {data.isPending ? (
        <Loading />
      ) : data.isError ? (
        <ErrorState error={data.error} retry={() => void data.refetch()} />
      ) : filtered.length === 0 ? (
        <div className="panel">
          <Empty
            icon={<Unplug size={26} />}
            title="Connect the systems you use"
            description="Add a bearer token, API key, basic authentication, or PostgreSQL connection."
          >
            {canAdmin && (
              <button className="button primary" onClick={() => open()}>
                <Plus size={16} />
                Add your first connection
              </button>
            )}
          </Empty>
        </div>
      ) : (
        <div className="connections-grid">
          {filtered.map((c) => (
            <article className="connection-card panel" key={c.id}>
              <div className="connection-top">
                <span
                  className={
                    "node-icon " + (c.type === "postgres" ? "cyan" : "violet")
                  }
                >
                  {c.type === "postgres" ? (
                    <Database size={22} />
                  ) : (
                    <KeyRound size={22} />
                  )}
                </span>
                <Status
                  value={
                    c.enabled
                      ? c.test_status === "FAILED"
                        ? "FAILED"
                        : "ACTIVE"
                      : "PAUSED"
                  }
                />
              </div>
              <h2>{c.name}</h2>
              <p>
                {c.type === "postgres"
                  ? "PostgreSQL database"
                  : c.type === "api_key"
                    ? "API key authentication"
                    : c.type === "basic"
                      ? "Basic authentication"
                      : "Bearer token"}
              </p>
              <dl className="compact-details">
                <dt>Scope</dt>
                <dd>Workspace</dd>
                <dt>Last checked</dt>
                <dd>{c.tested_at ? ago(c.tested_at) : "Not tested"}</dd>
                <dt>Last used</dt>
                <dd>{c.last_used_at ? ago(c.last_used_at) : "Not yet"}</dd>
                {c.type === "postgres" && (
                  <>
                    <dt>Database access</dt>
                    <dd>{c.allow_writes ? "Read and write" : "Read only"}</dd>
                  </>
                )}
              </dl>
              <footer>
                <span>
                  <LockKeyhole size={13} />
                  AES-GCM encrypted
                </span>
                {canAdmin && (
                  <div>
                    <button
                      className="icon-button"
                      title="Validate connection"
                      aria-label={"Test " + c.name}
                      onClick={async () => {
                        try {
                          const result = await post<{
                            message: string;
                            status: string;
                          }>("/connections/" + c.id + "/test");
                          toast(
                            result.message,
                            result.status === "FAILED" ? "error" : "success",
                          );
                          refresh("connections");
                        } catch (e) {
                          toast((e as Error).message, "error");
                        }
                      }}
                    >
                      <RefreshCw size={15} />
                    </button>
                    <button
                      className="icon-button"
                      title="Edit connection"
                      aria-label={"Edit " + c.name}
                      onClick={() => open(c)}
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      className="icon-button danger-hover"
                      title="Delete connection secret"
                      aria-label={"Delete " + c.name}
                      onClick={() => setDeleting(c)}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                )}
              </footer>
            </article>
          ))}
        </div>
      )}
      {dialog && (
        <Modal
          title={dialog === "new" ? "Add a connection" : "Edit connection"}
          onClose={() => setDialog(null)}
        >
          <form onSubmit={(e) => void submit(e)}>
            <label>
              Connection name
              <input
                name="name"
                defaultValue={dialog === "new" ? "" : dialog.name}
                placeholder="e.g. Inventory API"
                autoFocus
                required
                maxLength={120}
              />
            </label>
            <label>
              Authentication type
              <select
                value={kind}
                disabled={dialog !== "new"}
                onChange={(e) => setKind(e.target.value)}
              >
                <option value="bearer">Bearer token</option>
                <option value="api_key">API key header</option>
                <option value="basic">Basic authentication</option>
                <option value="postgres">PostgreSQL</option>
              </select>
            </label>
            {kind !== "postgres" && (
              <label>
                Approved API hostnames
                <input
                  name="allowedHosts"
                  defaultValue={
                    dialog === "new"
                      ? ""
                      : dialog.config.allowed_hosts?.join(", ") || ""
                  }
                  placeholder="api.example.com"
                  required
                />
                <small>
                  Comma-separated exact hosts. This credential can only
                  authenticate to these destinations.
                </small>
              </label>
            )}
            {dialog !== "new" && (
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={rotate}
                  onChange={(e) => setRotate(e.target.checked)}
                />
                Replace saved credentials
              </label>
            )}
            {(dialog === "new" || rotate) && (
              <div className="secret-fields">
                {["bearer", "api_key"].includes(kind) && (
                  <label>
                    Token
                    <input
                      type="password"
                      name="token"
                      required
                      autoComplete="off"
                    />
                  </label>
                )}
                {kind === "api_key" && (
                  <label>
                    Header name
                    <input name="header" defaultValue="X-API-Key" required />
                  </label>
                )}
                {kind === "postgres" && (
                  <>
                    <div className="form-row">
                      <label>
                        Hostname
                        <input
                          name="host"
                          placeholder="db.example.com"
                          required
                        />
                      </label>
                      <label>
                        Port
                        <input
                          name="port"
                          type="number"
                          defaultValue={5432}
                          min={1}
                          max={65535}
                          required
                        />
                      </label>
                    </div>
                    <label>
                      Database
                      <input name="database" placeholder="orders" required />
                    </label>
                  </>
                )}
                {["basic", "postgres"].includes(kind) && (
                  <>
                    <label>
                      Username
                      <input name="username" required autoComplete="off" />
                    </label>
                    <label>
                      Password
                      <input
                        type="password"
                        name="password"
                        required
                        autoComplete="new-password"
                      />
                    </label>
                  </>
                )}
                {kind === "postgres" && (
                  <label>
                    Transport encryption
                    <select name="sslmode" defaultValue="verify-full">
                      <option value="require">Require TLS</option>
                      <option value="verify-full">
                        Verify TLS and hostname
                      </option>
                      <option value="disable">
                        No TLS (approved local development only)
                      </option>
                    </select>
                  </label>
                )}
                <p className="small muted">
                  <LockKeyhole size={12} />
                  These fields will be encrypted and never displayed again.
                </p>
              </div>
            )}
            {kind === "postgres" && (
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  name="allowWrites"
                  defaultChecked={dialog !== "new" && dialog.allow_writes}
                />
                Allow write queries on this connection
              </label>
            )}
            <div className="modal-actions">
              <button
                className="button secondary"
                type="button"
                onClick={() => setDialog(null)}
              >
                Cancel
              </button>
              <button className="button primary" disabled={busy}>
                {busy ? "Saving…" : "Save connection"}
              </button>
            </div>
          </form>
        </Modal>
      )}
      {deleting && (
        <Modal
          title="Delete this connection secret?"
          onClose={() => setDeleting(null)}
        >
          <p>
            “{deleting.name}” will be disabled and its encrypted credential
            deleted. Workflows using it will fail until you provide a
            replacement.
          </p>
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setDeleting(null)}
            >
              Keep connection
            </button>
            <button
              className="button danger"
              onClick={async () => {
                try {
                  await remove("/connections/" + deleting.id);
                  setDeleting(null);
                  refresh("connections");
                  toast("Connection disabled and secret deleted.");
                } catch (e) {
                  toast((e as Error).message, "error");
                }
              }}
            >
              Delete secret
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
export function Schedules() {
  const { canEdit } = useWorkspace(),
    toast = useToast(),
    refresh = useRefresh();
  const data = useQuery({
    queryKey: ["schedules"],
    queryFn: () => api<Schedule[]>("/schedules"),
  });
  const workflows = useQuery({
    queryKey: ["workflows"],
    queryFn: () => api<Workflow[]>("/workflows?status=ACTIVE"),
  });
  const [open, setOpen] = useState(false),
    [cron, setCron] = useState("0 9 * * *"),
    [zone, setZone] = useState("Asia/Kolkata"),
    [preview, setPreview] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [deleting, setDeleting] = useState<Schedule | null>(null);
  async function previewTimes() {
    try {
      const result = await post<{
        next_runs: string[];
      }>("/schedules/preview", {
        cron,
        timezone: zone,
      });
      setPreview(result.next_runs);
    } catch (e) {
      toast((e as Error).message, "error");
      setPreview([]);
    }
  }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!preview.length) {
      toast("Preview the next five run times before saving.", "error");
      return;
    }
    setBusy(true);
    try {
      await post("/schedules", {
        workflow_id: new FormData(e.currentTarget).get("workflow"),
        cron,
        timezone: zone,
      });
      setOpen(false);
      refresh("schedules");
      toast("Schedule created.");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <PageHeading
        eyebrow="The right work, at the right time."
        title="Schedules"
        description="Timezone-aware schedules for your published workflows."
      >
        {canEdit && (
          <button
            className="button primary"
            onClick={() => {
              setOpen(true);
              setPreview([]);
            }}
          >
            <Plus size={16} />
            Add schedule
          </button>
        )}
      </PageHeading>
      <div className="info-banner warning-banner">
        <CalendarClock size={18} />
        <span>
          Unattended schedules require the continuous scheduler or an
          authenticated scheduler tick. Missed occurrences coalesce into one
          run.
        </span>
      </div>
      <section className="panel">
        {data.isPending ? (
          <Loading />
        ) : data.isError ? (
          <ErrorState error={data.error} />
        ) : data.data.length === 0 ? (
          <Empty
            icon={<CalendarClock size={26} />}
            title="Put recurring work on a schedule"
            description="Publish a workflow, choose a cron expression, and preview its next five run times."
          >
            {canEdit && (
              <button className="button primary" onClick={() => setOpen(true)}>
                <Plus size={15} />
                Create a schedule
              </button>
            )}
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Workflow</th>
                  <th>Schedule</th>
                  <th>Timezone</th>
                  <th>Next due</th>
                  <th>Last run</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.data.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <Link
                        className="table-name"
                        to={"/workflows/" + s.workflow_id}
                      >
                        <span className="table-icon">
                          <CalendarClock size={15} />
                        </span>
                        {s.workflow_name}
                      </Link>
                    </td>
                    <td>
                      <code>{s.cron}</code>
                    </td>
                    <td>{s.timezone}</td>
                    <td>{date(s.next_run_at)}</td>
                    <td>{date(s.last_run_at)}</td>
                    <td>
                      <Status value={s.enabled ? "ACTIVE" : "PAUSED"} />
                    </td>
                    <td>
                      {canEdit && (
                        <div className="table-actions">
                          <button
                            className="button secondary small-button"
                            onClick={async () => {
                              try {
                                await patch("/schedules/" + s.id, {
                                  enabled: !s.enabled,
                                });
                                refresh("schedules");
                              } catch (e) {
                                toast((e as Error).message, "error");
                              }
                            }}
                          >
                            {s.enabled ? "Pause" : "Enable"}
                          </button>
                          <button
                            className="icon-button danger-hover"
                            title="Delete schedule"
                            aria-label={
                              "Delete schedule for " + s.workflow_name
                            }
                            onClick={() => setDeleting(s)}
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {open && (
        <Modal title="Create a schedule" onClose={() => setOpen(false)}>
          <form onSubmit={(e) => void submit(e)}>
            <label>
              Published workflow
              <select name="workflow" required>
                <option value="">Select a workflow</option>
                {workflows.data?.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
              {workflows.data?.length === 0 && (
                <small>Publish and enable a workflow first.</small>
              )}
            </label>
            <label>
              Schedule
              <select
                value={
                  [
                    "0 * * * *",
                    "0 9 * * *",
                    "0 9 * * 1",
                    "*/15 * * * *",
                  ].includes(cron)
                    ? cron
                    : "custom"
                }
                onChange={(e) => {
                  if (e.target.value !== "custom") setCron(e.target.value);
                  else setCron("");
                  setPreview([]);
                }}
              >
                <option value="0 9 * * *">Daily at 09:00</option>
                <option value="0 * * * *">Every hour</option>
                <option value="*/15 * * * *">Every 15 minutes</option>
                <option value="0 9 * * 1">Every Monday at 09:00</option>
                <option value="custom">Custom cron</option>
              </select>
            </label>
            <label>
              Cron expression
              <input
                value={cron}
                onChange={(e) => {
                  setCron(e.target.value);
                  setPreview([]);
                }}
                placeholder="0 9 * * *"
                required
              />
            </label>
            <label>
              IANA timezone
              <input
                value={zone}
                onChange={(e) => {
                  setZone(e.target.value);
                  setPreview([]);
                }}
                placeholder="Asia/Kolkata"
                required
              />
            </label>
            <button
              type="button"
              className="button secondary full-width"
              onClick={() => void previewTimes()}
            >
              <CalendarClock size={15} />
              Preview next five runs
            </button>
            {preview.length > 0 && (
              <div className="schedule-preview">
                <h3>Next run times · {zone}</h3>
                {preview.map((v) => (
                  <div key={v}>
                    <CalendarClock size={13} />
                    {new Date(v).toLocaleString(undefined, {
                      timeZone: zone,
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </div>
                ))}
              </div>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="button secondary"
                onClick={() => setOpen(false)}
              >
                Cancel
              </button>
              <button
                className="button primary"
                disabled={busy || !preview.length}
              >
                Save schedule
              </button>
            </div>
          </form>
        </Modal>
      )}
      {deleting && (
        <Modal title="Remove this schedule?" onClose={() => setDeleting(null)}>
          <p>The workflow and its execution history remain available.</p>
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setDeleting(null)}
            >
              Keep schedule
            </button>
            <button
              className="button danger"
              onClick={async () => {
                try {
                  await remove("/schedules/" + deleting.id);
                  setDeleting(null);
                  refresh("schedules");
                  toast("Schedule removed.");
                } catch (e) {
                  toast((e as Error).message, "error");
                }
              }}
            >
              Remove schedule
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
export function Templates() {
  const { canEdit } = useWorkspace(),
    navigate = useNavigate(),
    toast = useToast(),
    [busy, setBusy] = useState("");
  const data = useQuery({
    queryKey: ["templates"],
    queryFn: () => api<Template[]>("/templates"),
  });
  async function createFromTemplate(t: Template) {
    setBusy(t.id);
    try {
      const w = await post<Workflow>("/workflows", {
        name: t.name,
        description: t.description,
        definition: t.definition,
      });
      navigate("/workflows/" + w.id);
      toast(
        "Template added as a draft. Review configuration before publishing.",
      );
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="page">
      <PageHeading
        eyebrow="A useful starting point."
        title="Workflow templates"
        description="Real patterns to adapt to your systems, with every step open for inspection."
      />
      {data.isPending ? (
        <Loading />
      ) : data.isError ? (
        <ErrorState error={data.error} />
      ) : (
        <div className="template-grid">
          {data.data.map((t, i) => (
            <article className="template-card" key={t.id}>
              <div className={"template-visual template-visual-" + i}>
                <div className="template-step">
                  <Globe size={20} />
                  <span>{t.definition.nodes[0].type}</span>
                </div>
                <div className="template-visual-line" />
                <div className="template-step">
                  <GitBranchIcon />
                  <span>Logic</span>
                </div>
                <div className="template-visual-line" />
                <div className="template-step">
                  <Network size={20} />
                  <span>Outcome</span>
                </div>
              </div>
              <div className="template-body">
                <span className="template-category">{t.category}</span>
                <h2>{t.name}</h2>
                <p>{t.description}</p>
                <div className="template-meta">
                  <span>
                    <Network size={13} />
                    {t.definition.nodes.length} nodes
                  </span>
                  <span>
                    <ShieldCheck size={13} />
                    Safe expressions
                  </span>
                </div>
                <details>
                  <summary>Sample input</summary>
                  <JsonView value={t.sample} />
                </details>
                <button
                  className="button secondary full-width"
                  disabled={!canEdit || !!busy}
                  onClick={() => void createFromTemplate(t)}
                >
                  {busy === t.id ? "Creating…" : "Use template"}
                  <ArrowUpRight size={15} />
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      <div className="template-note">
        <Boxes size={20} />
        <div>
          <strong>Make it your own.</strong>
          <p>
            Templates are drafts. The fulfillment demo requires your PostgreSQL
            connection and API destinations; the routing template runs with its
            sample input immediately.
          </p>
        </div>
      </div>
    </div>
  );
}
function GitBranchIcon() {
  return <Network size={20} />;
}
type Dead = {
  id: string;
  run_id: string;
  workflow_name: string;
  node_label: string | null;
  reason: string;
  attempts: number | null;
  created_at: string;
  resolved_at: string | null;
  recovery_run_id: string | null;
};
export function DeadLetters() {
  const { canEdit } = useWorkspace(),
    toast = useToast(),
    navigate = useNavigate(),
    refresh = useRefresh();
  const data = useQuery({
    queryKey: ["dead-letters"],
    queryFn: () => api<Dead[]>("/dead-letters"),
    refetchInterval: 10000,
  });
  const [showResolved, setShowResolved] = useState(false),
    [recovering, setRecovering] = useState<Dead | null>(null),
    [busy, setBusy] = useState(false);
  const items = data.data?.filter((d) => showResolved || !d.resolved_at) || [];
  return (
    <div className="page">
      <PageHeading
        eyebrow="Recover with the full context."
        title="Failed work"
        description="Failures stay visible until they’re resolved. Recovery creates a new execution."
      />
      <div className="list-toolbar">
        <span>
          {data.data?.filter((d) => !d.resolved_at).length || 0} unresolved
          failures
        </span>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={showResolved}
            onChange={(e) => setShowResolved(e.target.checked)}
          />
          Include resolved
        </label>
      </div>
      <section className="panel">
        {data.isPending ? (
          <Loading />
        ) : data.isError ? (
          <ErrorState error={data.error} />
        ) : items.length === 0 ? (
          <Empty
            icon={<CheckCircle2 size={28} />}
            title="Nothing needs recovery"
            description="Exhausted retries and permanent failures will appear here with their execution context."
          />
        ) : (
          <div className="failed-list">
            {items.map((item) => (
              <article key={item.id}>
                <div
                  className={
                    "failure-icon " + (item.resolved_at ? "resolved" : "")
                  }
                >
                  {item.resolved_at ? (
                    <CheckCircle2 size={21} />
                  ) : (
                    <TriangleAlert size={21} />
                  )}
                </div>
                <div>
                  <div className="failure-title">
                    <Link to={"/runs/" + item.run_id}>
                      {item.workflow_name}
                    </Link>
                    <Status
                      value={item.resolved_at ? "SUCCEEDED" : "FAILED"}
                      tiny
                    />
                  </div>
                  <p>{item.reason}</p>
                  <div className="failure-meta">
                    <code>{item.run_id.slice(0, 8)}</code>
                    <span>{item.node_label || "Execution"}</span>
                    <span>{item.attempts || 0} attempts</span>
                    <span>{date(item.created_at)}</span>
                  </div>
                </div>
                <div className="failure-actions">
                  <Link
                    className="button secondary small-button"
                    to={"/runs/" + item.run_id}
                  >
                    Inspect
                    <ArrowUpRight size={13} />
                  </Link>
                  {canEdit && !item.resolved_at && (
                    <>
                      <button
                        className="button secondary small-button"
                        onClick={() => setRecovering(item)}
                      >
                        <RotateCcw size={13} />
                        Re-run
                      </button>
                      <button
                        className="icon-button"
                        title="Mark resolved"
                        aria-label="Mark failure resolved"
                        onClick={async () => {
                          try {
                            await post("/dead-letters/" + item.id + "/resolve");
                            refresh("dead-letters");
                            toast("Failure marked resolved.");
                          } catch (e) {
                            toast((e as Error).message, "error");
                          }
                        }}
                      >
                        <Check size={17} />
                      </button>
                    </>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
      {recovering && (
        <Modal
          title="Create a recovery execution?"
          onClose={() => setRecovering(null)}
        >
          <p>
            “{recovering.workflow_name}” will run again with its original input
            and version. External actions may repeat; check downstream
            idempotency before continuing.
          </p>
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setRecovering(null)}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  const run = await post<{
                    run_id: string;
                  }>("/workflow-runs/" + recovering.run_id + "/rerun");
                  navigate("/runs/" + run.run_id);
                } catch (e) {
                  toast((e as Error).message, "error");
                } finally {
                  setBusy(false);
                  setRecovering(null);
                }
              }}
            >
              Start recovery
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
type AuditItem = {
  id: string;
  action: string;
  actor: string;
  resource_id: string | null;
  created_at: string;
  details: unknown;
};
export function AuditLog() {
  const { canAdmin } = useWorkspace(),
    [search, setSearch] = useState("");
  const data = useQuery({
    queryKey: ["audit"],
    queryFn: () => api<AuditItem[]>("/audit"),
    enabled: canAdmin,
  });
  if (!canAdmin)
    return (
      <ErrorState
        error={new Error("Administrator access is required for the audit log.")}
      />
    );
  return (
    <div className="page">
      <PageHeading
        eyebrow="A record of what changed."
        title="Audit log"
        description="Security and workspace events, without sensitive field values."
      />
      <div className="list-toolbar">
        <span className="muted">The 200 most recent events</span>
        <label className="search-field">
          <Search size={15} />
          <input
            aria-label="Search audit events"
            value={search}
            placeholder="Search actions or people…"
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      <div className="panel">
        {data.isPending ? (
          <Loading />
        ) : data.isError ? (
          <ErrorState error={data.error} />
        ) : data.data.length === 0 ? (
          <Empty
            icon={<FileClock size={26} />}
            title="Your history starts here"
            description="Workflow changes, sign-ins, and connection updates will be recorded automatically."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Actor</th>
                  <th>Resource</th>
                  <th>Time</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {data.data
                  .filter((a) =>
                    (a.action + " " + a.actor)
                      .toLowerCase()
                      .includes(search.toLowerCase()),
                  )
                  .map((a) => (
                    <tr key={a.id}>
                      <td>
                        <span className="audit-action">
                          <ShieldCheck size={15} />
                          {a.action.replaceAll(".", " ")}
                        </span>
                      </td>
                      <td>{a.actor}</td>
                      <td>
                        <code>{a.resource_id?.slice(0, 8) || "—"}</code>
                      </td>
                      <td className="muted">{date(a.created_at)}</td>
                      <td>
                        <code>{JSON.stringify(a.details)}</code>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
type Member = {
  id: string;
  display_name: string;
  email: string;
  role: string;
};
type Key = {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  expires_at: string;
  revoked_at: string | null;
  last_used_at: string | null;
};
export function Settings() {
  const { user, workspace, canAdmin } = useWorkspace(),
    toast = useToast(),
    refresh = useRefresh();
  const [tab, setTab] = useState("General"),
    [memberDialog, setMemberDialog] = useState(false),
    [keyDialog, setKeyDialog] = useState(false),
    [token, setToken] = useState(""),
    [revoking, setRevoking] = useState<Key | null>(null),
    [busy, setBusy] = useState(false),
    [workspaceDialog, setWorkspaceDialog] = useState(false),
    [removingMember, setRemovingMember] = useState<Member | null>(null);
  const members = useQuery({
    queryKey: ["members"],
    queryFn: () => api<Member[]>("/members"),
    enabled: canAdmin && tab === "Members",
  });
  const keys = useQuery({
    queryKey: ["api-keys"],
    queryFn: () => api<Key[]>("/api-keys"),
    enabled: canAdmin && tab === "API keys",
  });
  const info = useQuery({
    queryKey: ["system-info"],
    queryFn: () =>
      api<Record<string, string | number | boolean>>("/system/info"),
  });
  async function submitSettings(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    const form = new FormData(e.currentTarget);
    try {
      await patch("/settings", {
        name: form.get("name"),
        retention_days: Number(form.get("retention")),
      });
      refresh("me");
      toast("Workspace settings saved.");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page settings-page">
      <PageHeading
        eyebrow="Your workspace, your rules."
        title="Settings"
        description="Manage access, security, and the way your instance runs."
      />
      <div className="settings-layout">
        <nav className="settings-nav">
          {[
            ["General", Settings2],
            ["Members", Users],
            ["API keys", KeyRound],
            ["Security", ShieldCheck],
            ["System", Database],
          ]
            .filter(
              ([label]) =>
                canAdmin || !["Members", "API keys"].includes(label as string),
            )
            .map(([label, Icon]) => {
              const I = Icon as typeof Settings2;
              return (
                <button
                  key={label as string}
                  className={tab === label ? "active" : ""}
                  onClick={() => setTab(label as string)}
                >
                  <I size={17} />
                  {label as string}
                </button>
              );
            })}
        </nav>
        <section className="panel settings-panel">
          <div className="panel-header">
            <h2>{tab}</h2>
            {tab === "Members" && canAdmin && (
              <button
                className="button primary small-button"
                onClick={() => setMemberDialog(true)}
              >
                <Plus size={14} />
                Add member
              </button>
            )}
            {tab === "API keys" && canAdmin && (
              <button
                className="button primary small-button"
                onClick={() => {
                  setKeyDialog(true);
                  setToken("");
                }}
              >
                <Plus size={14} />
                Create API key
              </button>
            )}
          </div>
          {tab === "General" && (
            <div className="settings-body">
              <form onSubmit={(e) => void submitSettings(e)}>
                <label>
                  Workspace name
                  <input
                    name="name"
                    defaultValue={workspace.name}
                    required
                    maxLength={120}
                    disabled={!canAdmin}
                  />
                </label>
                <label>
                  Run metadata retention (days)
                  <input
                    name="retention"
                    type="number"
                    defaultValue={workspace.retention_days}
                    min={1}
                    max={3650}
                    required
                    disabled={!canAdmin}
                  />
                  <small>
                    Unresolved failures remain available until resolved.
                    Successful payloads expire after 30 days.
                  </small>
                </label>
                <div className="settings-row">
                  <span>Organization</span>
                  <strong>{workspace.organization_name}</strong>
                </div>
                <div className="settings-row">
                  <span>Environment</span>
                  <strong className="capitalize">
                    {workspace.environment}
                  </strong>
                </div>
                <div className="settings-row">
                  <span>Your role</span>
                  <strong className="capitalize">{workspace.role}</strong>
                </div>
                {canAdmin && (
                  <div className="modal-actions">
                    <button className="button primary" disabled={busy}>
                      Save changes
                    </button>
                  </div>
                )}
              </form>
              {canAdmin && (
                <div className="settings-divider">
                  <h3>Another environment</h3>
                  <p>
                    Keep workflows and connections separate across workspaces.
                  </p>
                  <button
                    className="button secondary"
                    onClick={() => setWorkspaceDialog(true)}
                  >
                    <Plus size={15} />
                    Create workspace
                  </button>
                </div>
              )}
            </div>
          )}
          {tab === "Members" &&
            (members.isPending ? (
              <Loading />
            ) : members.isError ? (
              <ErrorState error={members.error} />
            ) : (
              <div className="member-list">
                {members.data.map((m) => (
                  <div key={m.id}>
                    <span className="avatar">{m.display_name[0]}</span>
                    <div>
                      <strong>{m.display_name}</strong>
                      <span>{m.email}</span>
                    </div>
                    {workspace.role === "owner" && m.role !== "owner" ? (
                      <>
                        <select
                          aria-label={"Role for " + m.display_name}
                          value={m.role}
                          onChange={async (e) => {
                            try {
                              await patch("/members/" + m.id, {
                                role: e.target.value,
                              });
                              refresh("members");
                              toast(
                                "Member role updated. Existing API keys revoked.",
                              );
                            } catch (e) {
                              toast((e as Error).message, "error");
                            }
                          }}
                        >
                          {["admin", "editor", "viewer"].map((r) => (
                            <option key={r}>{r}</option>
                          ))}
                        </select>
                        <button
                          className="icon-button danger-hover"
                          aria-label={"Remove " + m.display_name}
                          onClick={() => setRemovingMember(m)}
                        >
                          <Trash2 size={15} />
                        </button>
                      </>
                    ) : (
                      <span className="tag capitalize">{m.role}</span>
                    )}
                  </div>
                ))}
              </div>
            ))}
          {tab === "API keys" &&
            (keys.isPending ? (
              <Loading />
            ) : keys.isError ? (
              <ErrorState error={keys.error} />
            ) : keys.data.length === 0 ? (
              <Empty
                icon={<KeyRound size={25} />}
                title="Access for your systems"
                description="Create scoped, expiring keys for programmatic workflow execution."
              />
            ) : (
              <div className="key-list">
                {keys.data.map((k) => (
                  <article key={k.id}>
                    <div>
                      <KeyRound size={18} />
                      <strong>{k.name}</strong>
                      <Status
                        value={
                          k.revoked_at || new Date(k.expires_at) <= new Date()
                            ? "PAUSED"
                            : "ACTIVE"
                        }
                        tiny
                      />
                    </div>
                    <code>{k.key_prefix}…</code>
                    <p>{k.scopes.join(", ")}</p>
                    <footer>
                      <span>Expires {date(k.expires_at)}</span>
                      {!k.revoked_at && (
                        <button
                          className="text-button error-text"
                          onClick={() => setRevoking(k)}
                        >
                          Revoke key
                        </button>
                      )}
                    </footer>
                  </article>
                ))}
              </div>
            ))}
          {tab === "Security" && (
            <div className="settings-body">
              <div className="security-item">
                <ShieldCheck size={22} />
                <div>
                  <h3>Secure sessions</h3>
                  <p>
                    HttpOnly cookies, rotating refresh tokens, CSRF protection,
                    and 30-minute access sessions.
                  </p>
                </div>
              </div>
              <div className="security-item">
                <LockKeyhole size={22} />
                <div>
                  <h3>Encrypted integration credentials</h3>
                  <p>
                    AES-GCM encryption with an instance master key. Secrets are
                    excluded from API responses and execution views.
                  </p>
                </div>
              </div>
              <div className="security-item">
                <Globe size={22} />
                <div>
                  <h3>Outbound network policy</h3>
                  <p>
                    Private destinations are blocked by default. DNS addresses
                    are checked and pinned for each request; redirects are
                    checked again.
                  </p>
                </div>
              </div>
              <div className="security-item">
                <KeyRound size={22} />
                <div>
                  <h3>Password reset delivery</h3>
                  <p>
                    {info.data?.email_configured
                      ? "SMTP delivery is configured."
                      : "SMTP delivery is not configured. An instance administrator can reset access using the local CLI."}
                  </p>
                </div>
              </div>
              <div className="settings-divider">
                <h3>Account sessions</h3>
                <p>Signed in as {user.email}.</p>
                <button
                  className="button secondary"
                  onClick={async () => {
                    try {
                      await post("/auth/logout-all");
                      queryClient.setQueryData(["me"], null);
                      toast("All account sessions revoked.");
                    } catch (e) {
                      toast((e as Error).message, "error");
                    }
                  }}
                >
                  Sign out of all sessions
                </button>
              </div>
            </div>
          )}
          {tab === "System" && (
            <div className="settings-body">
              <div className="system-logo">
                <Network size={32} />
                <div>
                  <h3>OxyBridge</h3>
                  <p>Connect systems. Orchestrate work. See every execution.</p>
                </div>
              </div>
              {info.isPending ? (
                <Loading />
              ) : info.isError ? (
                <ErrorState error={info.error} />
              ) : (
                <dl className="system-details">
                  {Object.entries(info.data)
                    .filter(([k]) => k !== "email_configured")
                    .map(([k, v]) => (
                      <div key={k}>
                        <dt>{k.replaceAll("_", " ")}</dt>
                        <dd>{String(v)}</dd>
                      </div>
                    ))}
                </dl>
              )}
              <div className="info-note">
                Short executions advance during requests. Durable retries and
                delays resume when the browser, cron, or an authenticated
                scheduler invokes the runtime. Run the continuous services for
                unattended processing.
              </div>
              <a
                className="button secondary"
                href="/docs"
                target="_blank"
                rel="noreferrer"
              >
                OpenAPI documentation
                <ArrowUpRight size={15} />
              </a>
            </div>
          )}
        </section>
      </div>
      {memberDialog && (
        <Modal
          title="Add a workspace member"
          onClose={() => setMemberDialog(false)}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              const values = Object.fromEntries(new FormData(e.currentTarget));
              setBusy(true);
              try {
                await post("/members", values);
                setMemberDialog(false);
                refresh("members");
                toast("Member added. Share their credentials privately.");
              } catch (e) {
                toast((e as Error).message, "error");
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Display name
              <input name="display_name" required maxLength={120} />
            </label>
            <label>
              Email
              <input name="email" type="email" required />
            </label>
            <label>
              Initial password
              <input
                name="password"
                type="password"
                minLength={12}
                required
                autoComplete="new-password"
              />
              <small>At least 12 characters. This is never shown again.</small>
            </label>
            <label>
              Role
              <select name="role" defaultValue="viewer">
                <option value="viewer">
                  Viewer · inspect workflows and runs
                </option>
                <option value="editor">
                  Editor · build and execute workflows
                </option>
                {workspace.role === "owner" && (
                  <option value="admin">
                    Admin · manage connections and members
                  </option>
                )}
              </select>
            </label>
            <div className="modal-actions">
              <button className="button primary" disabled={busy}>
                Add member
              </button>
            </div>
          </form>
        </Modal>
      )}
      {keyDialog && (
        <Modal
          title={token ? "Copy your API key" : "Create an API key"}
          onClose={() => setKeyDialog(false)}
        >
          {token ? (
            <>
              <p>
                This key is shown only once. Store it securely and send it as an
                Authorization: Bearer header.
              </p>
              <pre className="secret-once">{token}</pre>
              <button
                className="button primary"
                onClick={async () => {
                  await navigator.clipboard.writeText(token);
                  toast("API key copied.");
                }}
              >
                <Copy size={15} />
                Copy API key
              </button>
            </>
          ) : (
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                const form = new FormData(e.currentTarget);
                setBusy(true);
                try {
                  const result = await post<{
                    token: string;
                  }>("/api-keys", {
                    name: form.get("name"),
                    expires_days: Number(form.get("days")),
                    scopes: form.getAll("scopes"),
                  });
                  setToken(result.token);
                  refresh("api-keys");
                } catch (e) {
                  toast((e as Error).message, "error");
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label>
                Key name
                <input
                  name="name"
                  placeholder="e.g. Order service"
                  required
                  maxLength={120}
                />
              </label>
              <label>
                Expires in (days)
                <input
                  name="days"
                  type="number"
                  defaultValue={90}
                  min={1}
                  max={365}
                  required
                />
              </label>
              <fieldset>
                <legend>Allowed actions</legend>
                {[
                  ["workflows:read", "Read workflows"],
                  ["runs:read", "Inspect executions"],
                  ["runs:write", "Run and recover published workflows"],
                ].map(([value, label]) => (
                  <label className="checkbox-label" key={value}>
                    <input
                      name="scopes"
                      type="checkbox"
                      value={value}
                      defaultChecked={value === "runs:write"}
                    />
                    {label}
                  </label>
                ))}
              </fieldset>
              <div className="modal-actions">
                <button className="button primary" disabled={busy}>
                  Create API key
                </button>
              </div>
            </form>
          )}
        </Modal>
      )}
      {revoking && (
        <Modal title="Revoke this API key?" onClose={() => setRevoking(null)}>
          <p>
            “{revoking.name}” will lose access immediately. Systems using it
            need a replacement key.
          </p>
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setRevoking(null)}
            >
              Keep key
            </button>
            <button
              className="button danger"
              onClick={async () => {
                try {
                  await remove("/api-keys/" + revoking.id);
                  setRevoking(null);
                  refresh("api-keys");
                  toast("API key revoked.");
                } catch (e) {
                  toast((e as Error).message, "error");
                }
              }}
            >
              Revoke key
            </button>
          </div>
        </Modal>
      )}
      {workspaceDialog && (
        <Modal
          title="Create a workspace"
          onClose={() => setWorkspaceDialog(false)}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              const values = Object.fromEntries(new FormData(e.currentTarget));
              try {
                await post("/workspaces", values);
                setWorkspaceDialog(false);
                refresh("me");
                toast("Workspace created. Select it from the workspace menu.");
              } catch (e) {
                toast((e as Error).message, "error");
              }
            }}
          >
            <label>
              Workspace name
              <input
                name="name"
                required
                maxLength={120}
                placeholder="e.g. Staging"
              />
            </label>
            <label>
              Environment
              <select name="environment">
                <option value="development">Development</option>
                <option value="staging">Staging</option>
                <option value="production">Production</option>
              </select>
            </label>
            <div className="modal-actions">
              <button className="button primary">Create workspace</button>
            </div>
          </form>
        </Modal>
      )}
      {removingMember && (
        <Modal
          title="Remove this member?"
          onClose={() => setRemovingMember(null)}
        >
          <p>
            {removingMember.display_name} will lose access to all workspaces in
            this organization. Their API keys will be revoked.
          </p>
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setRemovingMember(null)}
            >
              Keep member
            </button>
            <button
              className="button danger"
              onClick={async () => {
                try {
                  await remove("/members/" + removingMember.id);
                  setRemovingMember(null);
                  refresh("members");
                  toast("Member removed.");
                } catch (e) {
                  toast((e as Error).message, "error");
                }
              }}
            >
              Remove member
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
