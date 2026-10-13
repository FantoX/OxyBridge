import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5000, retry: 1 } },
});
let workspace = localStorage.getItem("oxybridge:workspace") || "";
export function setWorkspace(id: string) {
  if (workspace === id) return;
  const user = queryClient.getQueryData(["me"]);
  workspace = id;
  localStorage.setItem("oxybridge:workspace", id);
  queryClient.clear();
  if (user) queryClient.setQueryData(["me"], user);
}
const csrf = () =>
  decodeURIComponent(
    document.cookie
      .split("; ")
      .find((v) => v.startsWith("ob_csrf="))
      ?.split("=")[1] || "",
  );
export class ApiError extends Error {
  status: number;
  code: string;
  errors?: import("./types").ValidationIssue[];
  constructor(
    status: number,
    detail: {
      message?: string;
      code?: string;
      errors?: import("./types").ValidationIssue[];
    },
  ) {
    super(detail.message || `Request failed (${status}).`);
    this.status = status;
    this.code = detail.code || "REQUEST_FAILED";
    this.errors = detail.errors;
  }
}
let refreshing: Promise<Response> | null = null;
export async function api<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const response = await fetch(
    path.startsWith("/hooks") ? path : "/api/v1" + path,
    {
      ...options,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf(),
        ...(workspace && !path.startsWith("/auth/")
          ? { "X-Workspace-ID": workspace }
          : {}),
        ...options.headers,
      },
    },
  );
  if (
    response.status === 401 &&
    retry &&
    csrf() &&
    (!path.startsWith("/auth/") || path === "/auth/me")
  ) {
    refreshing ||= fetch("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRF-Token": csrf() },
    }).finally(() => {
      refreshing = null;
    });
    const refresh = await refreshing;
    if (refresh.ok) return api(path, options, false);
    window.dispatchEvent(new Event("oxybridge:unauthorized"));
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(body.detail)
      ? {
          message: body.detail
            .map(
              (v: { loc: string[]; msg: string }) =>
                `${v.loc.slice(1).join(".")}: ${v.msg}`,
            )
            .join("; "),
        }
      : typeof body.detail === "string"
        ? { message: body.detail }
        : body.detail || {};
    throw new ApiError(response.status, detail);
  }
  return body as T;
}
export const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const remove = <T>(path: string) => api<T>(path, { method: "DELETE" });
export function download(name: string, data: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
