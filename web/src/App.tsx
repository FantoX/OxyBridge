import { Suspense, lazy, useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Link,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useOutletContext,
} from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Boxes,
  ChevronDown,
  CircleHelp,
  Command,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Network,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sun,
  Unplug,
  CalendarClock,
  BookOpen,
  TriangleAlert,
} from "lucide-react";
import { api, post, queryClient, setWorkspace } from "./api";
import type { User, Workspace, Workflow } from "./types";
import {
  ErrorState,
  Loading,
  Logo,
  Modal,
  ToastProvider,
  useToast,
} from "./ui";
import { Dashboard } from "./Dashboard";
import { Workflows } from "./Workflows";
const Builder = lazy(() =>
  import("./Builder").then((m) => ({ default: m.Builder })),
);
const Runs = lazy(() => import("./Runs").then((m) => ({ default: m.Runs })));
const RunDetail = lazy(() =>
  import("./Runs").then((m) => ({ default: m.RunDetail })),
);
const Connections = lazy(() =>
  import("./Management").then((m) => ({ default: m.Connections })),
);
const Schedules = lazy(() =>
  import("./Management").then((m) => ({ default: m.Schedules })),
);
const Templates = lazy(() =>
  import("./Management").then((m) => ({ default: m.Templates })),
);
const DeadLetters = lazy(() =>
  import("./Management").then((m) => ({ default: m.DeadLetters })),
);
const AuditLog = lazy(() =>
  import("./Management").then((m) => ({ default: m.AuditLog })),
);
const Settings = lazy(() =>
  import("./Management").then((m) => ({ default: m.Settings })),
);
export type ShellContext = {
  user: User;
  workspace: Workspace;
  canEdit: boolean;
  canAdmin: boolean;
};
export const useWorkspace = () => useOutletContext<ShellContext>();
function Authentication({ onLogin }: { onLogin: (user: User) => void }) {
  const status = useQuery({
    queryKey: ["auth-status"],
    queryFn: () =>
      api<{
        setup_required: boolean;
      }>("/auth/status"),
    retry: false,
  });
  const [mode, setMode] = useState<"login" | "forgot" | "reset">("login");
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const location = useLocation();
  useEffect(() => {
    if (location.pathname === "/reset-password") setMode("reset");
  }, [location.pathname]);
  const setup = status.data?.setup_required && mode === "login";
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    const values = Object.fromEntries(new FormData(e.currentTarget));
    try {
      if (mode === "forgot") {
        const result = await post<{
          message: string;
        }>("/auth/forgot-password", { email: values.email });
        setMessage(result.message);
      } else if (mode === "reset") {
        const result = await post<{
          message: string;
        }>("/auth/reset-password", {
          token: new URLSearchParams(location.search).get("token"),
          password: values.password,
        });
        setMessage(result.message);
        setMode("login");
      } else {
        const user = setup
          ? await api<User>("/auth/setup", {
              method: "POST",
              headers: { "X-Setup-Token": String(values.setupToken) },
              body: JSON.stringify({
                email: values.email,
                password: values.password,
                display_name: values.name,
                role: "viewer",
              }),
            })
          : await post<User>("/auth/login", {
              email: values.email,
              password: values.password,
            });
        setWorkspace(user.workspaces[0].id);
        onLogin(user);
      }
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Sign-in could not complete.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <section className="auth-story">
        <Logo />
        <div className="auth-story-body">
          <div className="auth-flow">
            <div>
              <Unplug size={24} />
            </div>
            <span />
            <div>
              <Network size={24} />
            </div>
            <span />
            <div>
              <ShieldCheck size={24} />
            </div>
          </div>
          <h1>
            Make your systems
            <br />
            work together.
          </h1>
          <p>
            Build the connection. Set the rules.
            <br />
            See every step, from event to outcome.
          </p>
          <div className="auth-caption">
            <span className="live-dot" />
            Your workflows. Your control.
          </div>
        </div>
        <span className="auth-footer">A FantoX product</span>
      </section>
      <section className="auth-form-panel">
        <form className="auth-form" onSubmit={submit}>
          <Logo small />
          <h2>
            {setup
              ? "Set up your workspace"
              : mode === "forgot"
                ? "Reset your password"
                : mode === "reset"
                  ? "Choose a new password"
                  : "Welcome back"}
          </h2>
          <p>
            {setup
              ? "Create the owner account for this OxyBridge instance."
              : mode === "forgot"
                ? "We’ll send a reset link if email delivery is configured."
                : mode === "reset"
                  ? "Use at least 12 characters for your new password."
                  : "Sign in to your OxyBridge workspace."}
          </p>
          {status.isError && (
            <ErrorState
              error={status.error}
              retry={() => void status.refetch()}
            />
          )}
          {setup && (
            <>
              <label>
                Display name
                <input
                  name="name"
                  autoComplete="name"
                  required
                  maxLength={120}
                />
              </label>
              <label>
                Instance setup token
                <input
                  name="setupToken"
                  type="password"
                  required
                  autoComplete="off"
                />
                <small>Use SETUP_TOKEN from your deployment environment.</small>
              </label>
            </>
          )}
          {mode !== "reset" && (
            <label>
              Email address
              <input
                type="email"
                name="email"
                placeholder="you@company.com"
                autoComplete="username"
                required
              />
            </label>
          )}
          {mode !== "forgot" && (
            <label>
              Password
              <input
                type="password"
                name="password"
                placeholder={
                  setup ? "At least 12 characters" : "Enter your password"
                }
                minLength={setup || mode === "reset" ? 12 : 1}
                maxLength={1024}
                autoComplete={
                  setup || mode === "reset"
                    ? "new-password"
                    : "current-password"
                }
                required
              />
            </label>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {message && (
            <p className="form-message" role="status">
              {message}
            </p>
          )}
          <button
            className="button primary auth-submit"
            disabled={busy || status.isError}
          >
            {busy
              ? "Please wait…"
              : setup
                ? "Create workspace"
                : mode === "forgot"
                  ? "Send reset link"
                  : mode === "reset"
                    ? "Update password"
                    : "Sign in"}
            <ArrowRight size={17} />
          </button>
          {!setup && (
            <button
              type="button"
              className="text-button"
              onClick={() => {
                setMode(mode === "login" ? "forgot" : "login");
                setError("");
              }}
            >
              {mode === "login" ? "Forgot your password?" : "Back to sign in"}
            </button>
          )}
          <div className="auth-security">
            <ShieldCheck size={14} />
            Secure sessions. Encrypted connections.
          </div>
        </form>
        <footer>
          OxyBridge v0.1.0 <span>Self-hosted workflow automation</span>
        </footer>
      </section>
    </main>
  );
}
const navigation = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/workflows", label: "Workflows", icon: Network },
  { to: "/runs", label: "Executions", icon: Activity },
  { to: "/connections", label: "Connections", icon: Unplug },
  { to: "/schedules", label: "Schedules", icon: CalendarClock },
  { to: "/templates", label: "Templates", icon: Boxes },
];
function Shell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const stored = localStorage.getItem("oxybridge:workspace");
  const [workspaceId, selectWorkspace] = useState(
    user.workspaces.some((w) => w.id === stored)
      ? stored!
      : user.workspaces[0].id,
  );
  const workspace =
    user.workspaces.find((w) => w.id === workspaceId) || user.workspaces[0];
  useEffect(() => {
    setWorkspace(workspace.id);
  }, [workspace.id]);
  const canEdit = workspace.role !== "viewer",
    canAdmin = ["owner", "admin"].includes(workspace.role);
  const [mobile, setMobile] = useState(false),
    [editorDirty, setEditorDirty] = useState(false),
    [searchOpen, setSearchOpen] = useState(false),
    [term, setTerm] = useState(""),
    [help, setHelp] = useState(false);
  const [theme, setTheme] = useState(
    localStorage.getItem("oxybridge:theme") || "light",
  );
  const location = useLocation(),
    navigate = useNavigate(),
    toast = useToast();
  const isBuilder = /^\/workflows\/[^/]+$/.test(location.pathname);
  useEffect(() => {
    const handler = (e: Event) =>
      setEditorDirty((e as CustomEvent<boolean>).detail);
    window.addEventListener("oxybridge:draft-state", handler);
    return () => window.removeEventListener("oxybridge:draft-state", handler);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("oxybridge:theme", theme);
  }, [theme]);
  useEffect(() => {
    setMobile(false);
  }, [location.pathname]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  const workflows = useQuery({
    queryKey: ["search-workflows", workspaceId, term],
    queryFn: () =>
      api<Workflow[]>("/workflows?search=" + encodeURIComponent(term)),
    enabled: searchOpen,
  });
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
  async function logout() {
    try {
      await post("/auth/logout");
      onLogout();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  return (
    <div className={`app-shell ${isBuilder ? "builder-shell" : ""}`}>
      <aside className={`sidebar ${mobile ? "mobile-open" : ""}`}>
        <Link to="/" className="brand-link" aria-label="OxyBridge overview">
          <Logo />
        </Link>
        <div className="workspace-picker">
          <div className="workspace-avatar">F</div>
          <div>
            <span className="workspace-caption">Workspace</span>
            <select
              aria-label="Switch workspace"
              value={workspaceId}
              disabled={editorDirty}
              title={
                editorDirty
                  ? "Save or discard your edits before switching workspaces"
                  : undefined
              }
              onChange={(e) => {
                selectWorkspace(e.target.value);
                setWorkspace(e.target.value);
                navigate("/");
              }}
            >
              {user.workspaces.map((w) => (
                <option value={w.id} key={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
          <ChevronDown size={13} />
        </div>
        {canEdit && (
          <button
            className="button primary new-workflow"
            onClick={() => void create()}
          >
            <Plus size={17} />
            New workflow
          </button>
        )}
        <div className="nav-label">Workspace</div>
        <nav>
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"} aria-label={label}>
              <Icon size={18} />
              <span>{label}</span>
              {label === "Workflows" && (
                <span className="nav-shortcut">
                  <Command size={10} />K
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="nav-label nav-section">Monitor</div>
        <nav>
          <NavLink to="/failed">
            <TriangleAlert size={18} />
            <span>Failed work</span>
          </NavLink>
          {canAdmin && (
            <NavLink to="/audit">
              <ShieldCheck size={18} />
              <span>Audit log</span>
            </NavLink>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="instance-label">
            <span className="live-dot" />
            <span>PostgreSQL</span>
            <span className="muted">v0.1</span>
          </div>
          <nav>
            <NavLink to="/settings">
              <Settings2 size={18} />
              <span>Settings</span>
            </NavLink>
            <button onClick={() => setHelp(true)}>
              <CircleHelp size={18} />
              <span>Help & shortcuts</span>
            </button>
          </nav>
          <div className="profile">
            <div className="avatar">
              {user.display_name
                .split(" ")
                .map((v) => v[0])
                .slice(0, 2)
                .join("")}
            </div>
            <div>
              <strong>{user.display_name}</strong>
              <span>
                {workspace.role.charAt(0).toUpperCase() +
                  workspace.role.slice(1)}
              </span>
            </div>
            <button
              className="icon-button"
              onClick={() => void logout()}
              aria-label="Sign out"
              disabled={editorDirty}
              title="Sign out"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      {mobile && (
        <button
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="Open navigation"
            onClick={() => setMobile(true)}
          >
            <Menu size={20} />
          </button>
          <div className="breadcrumb">
            <span>{workspace.organization_name}</span>
            <span className="slash">/</span>
            <strong>
              {isBuilder
                ? "Workflow editor"
                : navigation.find((n) => n.to === location.pathname)?.label ||
                  (location.pathname.startsWith("/runs/")
                    ? "Execution detail"
                    : location.pathname === "/failed"
                      ? "Failed work"
                      : location.pathname === "/audit"
                        ? "Audit log"
                        : "Settings")}
            </strong>
          </div>
          <div className="topbar-actions">
            <button
              className="search-trigger"
              aria-label="Search workflows"
              onClick={() => setSearchOpen(true)}
            >
              <Search size={15} />
              <span>Search workflows</span>
              <kbd>⌘ K</kbd>
            </button>
            <span className="environment">
              <span className="live-dot" />
              {workspace.environment}
            </span>
            <button
              className="icon-button"
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
              aria-label={
                theme === "light"
                  ? "Switch to dark theme"
                  : "Switch to light theme"
              }
              title="Toggle theme"
            >
              {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
            </button>
            <div className="avatar top-avatar">{user.display_name[0]}</div>
          </div>
        </header>
        <div
          className={`main-content ${isBuilder ? "canvas-content" : ""}`}
          key={workspaceId}
        >
          <Suspense fallback={<Loading />}>
            <Outlet
              context={
                { user, workspace, canEdit, canAdmin } satisfies ShellContext
              }
            />
          </Suspense>
        </div>
      </div>
      {searchOpen && (
        <Modal title="Find a workflow" onClose={() => setSearchOpen(false)}>
          <label className="search-modal-input">
            <Search size={18} />
            <input
              autoFocus
              placeholder="Search by workflow name…"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
            />
          </label>
          <div className="search-results">
            {workflows.data?.map((w) => (
              <button
                key={w.id}
                onClick={() => {
                  navigate("/workflows/" + w.id);
                  setSearchOpen(false);
                }}
              >
                <Network size={18} />
                <span>{w.name}</span>
                <ArrowRight size={16} />
              </button>
            ))}
            {workflows.data?.length === 0 && (
              <p>No workflows match your search.</p>
            )}
          </div>
        </Modal>
      )}
      {help && (
        <Modal
          title="A little help goes a long way"
          onClose={() => setHelp(false)}
        >
          <div className="help-content">
            <p>
              Build a workflow, validate its configuration, then publish an
              immutable version. Test runs use a snapshot of your draft and can
              perform real API actions.
            </p>
            <h3>Editor shortcuts</h3>
            <dl>
              <dt>Find workflows</dt>
              <dd>
                <kbd>Ctrl / ⌘ K</kbd>
              </dd>
              <dt>Undo / redo</dt>
              <dd>
                <kbd>Ctrl / ⌘ Z</kbd> <kbd>Shift Z</kbd>
              </dd>
              <dt>Copy / paste nodes</dt>
              <dd>
                <kbd>Ctrl / ⌘ C</kbd> <kbd>V</kbd>
              </dd>
              <dt>Remove selection</dt>
              <dd>
                <kbd>Delete</kbd>
              </dd>
              <dt>Select multiple nodes</dt>
              <dd>
                <kbd>Shift + click</kbd>
              </dd>
            </dl>
            <p>
              Schedules and delayed retries advance when the scheduler is
              invoked. Run the continuous scheduler or configure an
              authenticated scheduler tick for unattended work.
            </p>
            <a
              className="button secondary"
              href="/docs"
              target="_blank"
              rel="noreferrer"
            >
              <BookOpen size={16} />
              API documentation
            </a>
          </div>
        </Modal>
      )}
    </div>
  );
}
function Application() {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/auth/me"),
    retry: false,
  });
  const navigate = useNavigate();
  useEffect(() => {
    const handler = () => {
      queryClient.setQueryData(["me"], null);
      navigate("/login");
    };
    window.addEventListener("oxybridge:unauthorized", handler);
    return () => window.removeEventListener("oxybridge:unauthorized", handler);
  }, [navigate]);
  if (me.isPending) return <Loading />;
  if (me.isError && !("status" in me.error && me.error.status === 401))
    return (
      <div className="startup-error">
        <Logo />
        <ErrorState error={me.error} retry={() => void me.refetch()} />
      </div>
    );
  if (!me.data)
    return (
      <Authentication
        onLogin={(user) => {
          queryClient.setQueryData(["me"], user);
          navigate("/");
        }}
      />
    );
  return (
    <Routes>
      <Route
        element={
          <Shell
            user={me.data}
            onLogout={() => {
              queryClient.clear();
              queryClient.setQueryData(["me"], null);
              navigate("/login");
            }}
          />
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="workflows" element={<Workflows />} />
        <Route path="workflows/:id" element={<Builder />} />
        <Route path="runs" element={<Runs />} />
        <Route path="runs/:id" element={<RunDetail />} />
        <Route path="connections" element={<Connections />} />
        <Route path="schedules" element={<Schedules />} />
        <Route path="templates" element={<Templates />} />
        <Route path="failed" element={<DeadLetters />} />
        <Route path="audit" element={<AuditLog />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Dashboard />} />
      </Route>
    </Routes>
  );
}
export function App() {
  return (
    <ToastProvider>
      <Application />
    </ToastProvider>
  );
}
