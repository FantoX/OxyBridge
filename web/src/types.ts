export type Config = Record<string, unknown>;
export type GraphNode = {
  id: string;
  type: string;
  label: string;
  alias?: string;
  position: { x: number; y: number };
  config: Config;
};
export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
};
export type Definition = {
  schema_version: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
};
export type Workflow = {
  id: string;
  name: string;
  description: string;
  workspace_id: string;
  status: string;
  revision: number;
  definition: Definition;
  active_version_id: string | null;
  updated_at: string;
  version_number?: number;
  success_rate?: number | null;
  last_run?: Run | null;
  webhook_enabled?: boolean;
};
export type Attempt = {
  id: string;
  number: number;
  status: string;
  duration_ms: number | null;
  created_at: string;
  error: string | null;
  http_status: number | null;
};
export type NodeRun = {
  id: string;
  node_id: string;
  node_type: string;
  label: string;
  status: string;
  attempt: number;
  input_data: unknown;
  output_data: unknown;
  error: string | null;
  error_code: string | null;
  duration_ms: number | null;
  started_at: string | null;
  finished_at: string | null;
  next_attempt_at: string | null;
  worker_id: string | null;
  queue: string;
  attempts: Attempt[];
};
export type Run = {
  id: string;
  workflow_id: string;
  workflow_name: string;
  version_id: string;
  version_number: number;
  is_test: boolean;
  status: string;
  trigger_type: string;
  trigger_payload: unknown;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  error_code: string | null;
  retries: number;
  nodes?: NodeRun[];
  definition?: Definition;
  recovery_of: string | null;
};
export type Workspace = {
  id: string;
  name: string;
  organization_name: string;
  organization_id: string;
  environment: string;
  role: string;
  retention_days: number;
};
export type User = {
  id: string;
  email: string;
  display_name: string;
  workspaces: Workspace[];
};
export type Connection = {
  id: string;
  name: string;
  type: string;
  config: { allowed_hosts?: string[] };
  enabled: boolean;
  allow_writes: boolean;
  tested_at: string | null;
  test_status: string | null;
  last_used_at: string | null;
};
export type Schedule = {
  id: string;
  workflow_id: string;
  workflow_name: string;
  cron: string;
  timezone: string;
  enabled: boolean;
  next_run_at: string;
  last_run_at: string | null;
};
export type ValidationIssue = {
  code: string;
  message: string;
  node_id: string | null;
  field: string | null;
};
export type Validation = {
  valid: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
};
export type Template = {
  id: string;
  name: string;
  description: string;
  category: string;
  definition: Definition;
  sample: Config;
};
export type DashboardData = {
  runs_today: number;
  active_workflows: number;
  success_rate: number | null;
  failed_runs: number;
  queued: number;
  avg_duration_ms: number | null;
  p95_duration_ms: number | null;
  hours: {
    time: string;
    succeeded: number;
    failed: number;
    total: number;
    latency_ms: number;
  }[];
  recent_runs: Run[];
  health: {
    database: string;
    runtime: string;
    services: { name: string; seen_at: string }[];
  };
};
export const terminal = (status: string) =>
  ["SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"].includes(status);
