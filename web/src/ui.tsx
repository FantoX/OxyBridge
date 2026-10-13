import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  Check,
  CheckCircle2,
  AlertCircle,
  X,
  LoaderCircle,
  Circle,
  Clock3,
  Ban,
} from "lucide-react";

type Toast = {
  id: number;
  message: string;
  kind: "success" | "error" | "info";
};
const ToastContext = createContext<
  (message: string, kind?: Toast["kind"]) => void
>(() => {});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const notify = useCallback(
    (message: string, kind: Toast["kind"] = "success") => {
      const id = Date.now() + Math.random();
      setItems((v) => [...v.slice(-2), { id, message, kind }]);
      window.setTimeout(
        () => setItems((v) => v.filter((t) => t.id !== id)),
        6000,
      );
    },
    [],
  );
  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => (
          <div className={`toast ${t.kind}`} key={t.id}>
            {t.kind === "error" ? (
              <AlertCircle size={18} />
            ) : (
              <CheckCircle2 size={18} />
            )}
            <span>{t.message}</span>
            <button
              className="icon-button"
              aria-label="Dismiss notification"
              onClick={() => setItems((v) => v.filter((i) => i.id !== t.id))}
            >
              <X size={16} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
export const useToast = () => useContext(ToastContext);
export function Logo({ small = false }: { small?: boolean }) {
  return (
    <div className={`brand ${small ? "small" : ""}`}>
      <svg
        width="32"
        height="32"
        viewBox="0 0 32 32"
        fill="none"
        aria-hidden="true"
      >
        <rect x="1" y="1" width="30" height="30" rx="9" fill="currentColor" />
        <path
          d="M8 20V15C8 10 13 8 16 8C19 8 24 10 24 15V20M8 17H24M12 24V17M20 24V17"
          stroke="white"
          strokeWidth="2.2"
          strokeLinecap="round"
        />
      </svg>
      {!small && (
        <span>
          OxyBridge<span className="brand-dot">.</span>
        </span>
      )}
    </div>
  );
}
const statusNames: Record<string, string> = {
  ACTIVE: "Active",
  DRAFT: "Draft",
  PAUSED: "Paused",
  ARCHIVED: "Archived",
  QUEUED: "Queued",
  RUNNING: "Running",
  SUCCEEDED: "Succeeded",
  FAILED: "Failed",
  RETRY_WAIT: "Retrying",
  PENDING: "Pending",
  SKIPPED: "Skipped",
  CANCEL_REQUESTED: "Cancelling",
  CANCELLED: "Cancelled",
  TIMED_OUT: "Timed out",
  VALID: "Valid",
};
export function Status({
  value,
  tiny = false,
}: {
  value: string;
  tiny?: boolean;
}) {
  const Icon = ["SUCCEEDED", "ACTIVE", "VALID"].includes(value)
    ? Check
    : ["FAILED", "TIMED_OUT"].includes(value)
      ? AlertCircle
      : ["RUNNING", "QUEUED"].includes(value)
        ? LoaderCircle
        : value === "RETRY_WAIT"
          ? Clock3
          : value === "CANCELLED"
            ? Ban
            : Circle;
  return (
    <span
      className={`status status-${value.toLowerCase()} ${tiny ? "tiny" : ""}`}
    >
      <Icon size={tiny ? 11 : 13} />
      {statusNames[value] || value}
    </span>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      className={`modal ${wide ? "wide" : ""}`}
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="modal-title">
        <h2>{title}</h2>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Loading({
  label = "Loading your workspace…",
}: {
  label?: string;
}) {
  return (
    <div className="loading">
      <LoaderCircle className="spin" size={24} />
      <p>{label}</p>
    </div>
  );
}
export function Empty({
  icon,
  title,
  description,
  children,
}: {
  icon?: ReactNode;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty-state">
      {icon && <div className="empty-icon">{icon}</div>}
      <h3>{title}</h3>
      <p>{description}</p>
      {children}
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div className="error-state" role="alert">
      <AlertCircle size={22} />
      <div>
        <strong>Could not load this view</strong>
        <p>
          {error instanceof Error ? error.message : "Try refreshing this page."}
        </p>
        {retry && (
          <button className="button secondary" onClick={retry}>
            Try again
          </button>
        )}
      </div>
    </div>
  );
}
export const duration = (ms: number | null | undefined) =>
  ms == null
    ? "—"
    : ms < 1000
      ? `${ms} ms`
      : `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
export const date = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
export function ago(value: string) {
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  return seconds < 60
    ? "Just now"
    : seconds < 3600
      ? `${Math.floor(seconds / 60)}m ago`
      : seconds < 86400
        ? `${Math.floor(seconds / 3600)}h ago`
        : `${Math.floor(seconds / 86400)}d ago`;
}
export function JsonView({ value }: { value: unknown }) {
  return (
    <pre className="json-view">
      {value === undefined || value === null
        ? "No data recorded."
        : JSON.stringify(value, null, 2)}
    </pre>
  );
}
