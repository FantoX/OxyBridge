import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  Copy,
  Download,
  Network,
  Pause,
  Play,
  Plus,
  Search,
  Trash2,
  Upload,
  Zap,
} from "lucide-react";
import { api, download, post, queryClient, remove } from "./api";
import { useWorkspace } from "./App";
import type { Workflow } from "./types";
import { ago, Empty, ErrorState, Loading, Modal, Status, useToast } from "./ui";

export function Workflows() {
  const { canEdit } = useWorkspace(),
    toast = useToast(),
    navigate = useNavigate();
  const [search, setSearch] = useState(""),
    [status, setStatus] = useState(""),
    [name, setName] = useState(""),
    [creating, setCreating] = useState(false),
    [busy, setBusy] = useState(false),
    [archive, setArchive] = useState<Workflow | null>(null),
    [running, setRunning] = useState<Workflow | null>(null),
    [payload, setPayload] = useState("{}");
  const upload = useRef<HTMLInputElement>(null);
  const workflows = useQuery({
    queryKey: ["workflows", search, status],
    queryFn: () =>
      api<Workflow[]>(
        `/workflows?search=${encodeURIComponent(search)}&status=${status}`,
      ),
  });
  async function create() {
    setBusy(true);
    try {
      const w = await post<Workflow>("/workflows", { name });
      await queryClient.invalidateQueries({ queryKey: ["workflows"] });
      navigate("/workflows/" + w.id);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function action(w: Workflow, kind: string) {
    try {
      if (kind === "duplicate") {
        const next = await post<Workflow>("/workflows", {
          name: w.name.slice(0, 113) + " (copy)",
          description: w.description,
          definition: w.definition,
        });
        navigate("/workflows/" + next.id);
      } else if (kind === "export")
        download(
          w.name.replace(/[^a-z0-9]/gi, "-") + ".json",
          await api("/workflows/" + w.id + "/export"),
        );
      else {
        await post("/workflows/" + w.id + "/" + kind);
        toast(kind === "pause" ? "Workflow paused." : "Workflow enabled.");
      }
      void queryClient.invalidateQueries({ queryKey: ["workflows"] });
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  async function importFile(file: File) {
    try {
      if (file.size > 1_000_000)
        throw new Error("Workflow imports must be smaller than 1 MB.");
      const data = JSON.parse(await file.text());
      if (
        data.format !== "OxyBridge-workflow" ||
        data.format_version !== 1 ||
        !data.workflow?.definition?.nodes ||
        !data.workflow?.definition?.edges
      )
        throw new Error(
          "Choose an OxyBridge workflow export (format version 1).",
        );
      const w = await post<Workflow>("/workflows", data.workflow);
      navigate("/workflows/" + w.id);
      toast(
        "Workflow imported as a draft. Review credential references before publishing.",
      );
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="greeting">Build once. Let it flow.</div>
          <h1>Workflows</h1>
          <p>Connect your systems with clear, inspectable automation.</p>
        </div>
        {canEdit && (
          <div className="heading-actions">
            <button
              className="button secondary"
              onClick={() => upload.current?.click()}
            >
              <Upload size={15} />
              Import
            </button>
            <button
              className="button primary"
              onClick={() => setCreating(true)}
            >
              <Plus size={16} />
              Create workflow
            </button>
            <input
              hidden
              type="file"
              ref={upload}
              accept="application/json,.json"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void importFile(f);
                e.target.value = "";
              }}
            />
          </div>
        )}
      </div>
      <div className="list-toolbar">
        <div className="filter-tabs">
          {[
            ["", "All workflows"],
            ["ACTIVE", "Active"],
            ["DRAFT", "Drafts"],
            ["PAUSED", "Paused"],
            ["ARCHIVED", "Archived"],
          ].map(([v, l]) => (
            <button
              key={v}
              className={status === v ? "active" : ""}
              onClick={() => setStatus(v)}
            >
              {l}
            </button>
          ))}
        </div>
        <label className="search-field">
          <Search size={16} />
          <input
            aria-label="Search workflows"
            placeholder="Search workflows…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      {workflows.isPending ? (
        <Loading />
      ) : workflows.isError ? (
        <ErrorState
          error={workflows.error}
          retry={() => void workflows.refetch()}
        />
      ) : workflows.data.length === 0 ? (
        <div className="panel">
          <Empty
            icon={<Network size={26} />}
            title={
              search
                ? "No matching workflows"
                : "Your next connection starts here"
            }
            description={
              search
                ? "Try another workflow name."
                : "Create a workflow from scratch or begin with a template."
            }
          >
            <Link className="button primary" to="/templates">
              Explore templates
            </Link>
          </Empty>
        </div>
      ) : (
        <div className="workflow-grid">
          {workflows.data.map((w, i) => (
            <article className="workflow-card" key={w.id}>
              <div className="workflow-card-top">
                <span className={`workflow-tile tile-${i % 3}`}>
                  <Network size={20} />
                </span>
                <Status value={w.status} />
              </div>
              <Link to={"/workflows/" + w.id}>
                <h2>{w.name}</h2>
              </Link>
              <p>
                {w.description ||
                  "Add a description to explain what this workflow does."}
              </p>
              <div className="workflow-card-path">
                <span>
                  <Zap size={13} />
                  {w.definition.nodes.find((n) =>
                    ["manual", "webhook", "schedule", "api"].includes(n.type),
                  )?.type || "No trigger"}
                </span>
                <span>{w.definition.nodes.length} nodes</span>
                <span>
                  {w.version_number
                    ? `Published v${w.version_number}`
                    : "Unpublished"}
                </span>
              </div>
              <div className="workflow-card-stats">
                <div>
                  <span>Last execution</span>
                  <strong>
                    {w.last_run ? (
                      <Status value={w.last_run.status} tiny />
                    ) : (
                      "No runs yet"
                    )}
                  </strong>
                </div>
                <div>
                  <span>7d success</span>
                  <strong>
                    {w.success_rate == null ? "—" : w.success_rate + "%"}
                  </strong>
                </div>
              </div>
              <div className="workflow-card-footer">
                <span>Edited {ago(w.updated_at)}</span>
                <div>
                  {canEdit && (
                    <>
                      {w.status === "ACTIVE" && (
                        <button
                          className="icon-button"
                          title="Run published workflow"
                          aria-label={"Run " + w.name}
                          onClick={() => {
                            setRunning(w);
                            setPayload(
                              w.name.toLowerCase().includes("order")
                                ? '{"order_id":"ORD-2041","total":749,"customer":{"email":"customer@example.com"}}'
                                : "{}",
                            );
                          }}
                        >
                          <Play size={15} />
                        </button>
                      )}
                      <button
                        className="icon-button"
                        title="Duplicate workflow"
                        aria-label={"Duplicate " + w.name}
                        onClick={() => void action(w, "duplicate")}
                      >
                        <Copy size={15} />
                      </button>
                      {(w.active_version_id || w.status === "ARCHIVED") && (
                        <button
                          className="icon-button"
                          title={
                            w.status === "ACTIVE"
                              ? "Pause workflow"
                              : "Enable workflow"
                          }
                          aria-label={
                            w.status === "ACTIVE"
                              ? "Pause workflow"
                              : "Enable workflow"
                          }
                          onClick={() =>
                            void action(
                              w,
                              w.status === "ACTIVE" ? "pause" : "resume",
                            )
                          }
                        >
                          {w.status === "ACTIVE" ? (
                            <Pause size={15} />
                          ) : (
                            <Play size={15} />
                          )}
                        </button>
                      )}
                      <button
                        className="icon-button danger-hover"
                        title="Archive workflow"
                        aria-label={"Archive " + w.name}
                        onClick={() => setArchive(w)}
                      >
                        <Trash2 size={15} />
                      </button>
                    </>
                  )}
                  <button
                    className="icon-button"
                    title="Export workflow"
                    aria-label={"Export " + w.name}
                    onClick={() => void action(w, "export")}
                  >
                    <Download size={15} />
                  </button>
                  <Link
                    className="icon-button"
                    to={"/workflows/" + w.id}
                    aria-label={"Open " + w.name}
                  >
                    <ArrowUpRight size={17} />
                  </Link>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
      {creating && (
        <Modal title="Create a workflow" onClose={() => setCreating(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void create();
            }}
          >
            <label>
              Workflow name
              <input
                autoFocus
                placeholder="e.g. Customer onboarding"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={120}
              />
            </label>
            <p className="muted">
              Start with an empty canvas. Add a trigger, then connect the steps
              that follow.
            </p>
            <div className="modal-actions">
              <button
                className="button secondary"
                type="button"
                onClick={() => setCreating(false)}
              >
                Cancel
              </button>
              <button className="button primary" disabled={busy}>
                {busy ? "Creating…" : "Create workflow"}
              </button>
            </div>
          </form>
        </Modal>
      )}
      {running && (
        <Modal title="Run published workflow" onClose={() => setRunning(null)}>
          <p>
            Run “{running.name}” using its active published version. Actions can
            make real API calls and database writes.
          </p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                const input = JSON.parse(payload);
                if (!input || Array.isArray(input) || typeof input !== "object")
                  throw new Error("Enter a JSON object.");
                const r = await post<{ run_id: string }>(
                  "/workflows/" + running.id + "/run",
                  { payload: input },
                );
                navigate("/runs/" + r.run_id);
              } catch (e) {
                toast((e as Error).message, "error");
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Input payload
              <textarea
                className="code-input"
                rows={9}
                value={payload}
                onChange={(e) => setPayload(e.target.value)}
                spellCheck={false}
              />
            </label>
            <div className="modal-actions">
              <button
                className="button secondary"
                type="button"
                onClick={() => setRunning(null)}
              >
                Cancel
              </button>
              <button className="button primary" disabled={busy}>
                <Play size={14} />
                Start execution
              </button>
            </div>
          </form>
        </Modal>
      )}
      {archive && (
        <Modal title="Archive this workflow?" onClose={() => setArchive(null)}>
          <p>
            “{archive.name}” will stop accepting new triggers. Execution history
            remains available, and you can enable it again from Archived.
          </p>
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setArchive(null)}
            >
              Keep workflow
            </button>
            <button
              className="button danger"
              onClick={async () => {
                try {
                  await remove("/workflows/" + archive.id);
                  setArchive(null);
                  toast("Workflow archived.");
                  void queryClient.invalidateQueries({
                    queryKey: ["workflows"],
                  });
                } catch (e) {
                  toast((e as Error).message, "error");
                }
              }}
            >
              Archive workflow
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
