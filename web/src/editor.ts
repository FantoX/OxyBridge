import { create } from "zustand";
import {
  applyEdgeChanges,
  applyNodeChanges,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import type { Definition, GraphNode } from "./types";

export type EditorNode = Node<
  {
    kind: string;
    label: string;
    alias: string;
    config: GraphNode["config"];
    status?: string;
    error?: string;
  },
  "workflow"
>;
type Snapshot = { nodes: EditorNode[]; edges: Edge[] };
type State = Snapshot & {
  invalidFields: Record<string, { raw: string; error: string }>;
  setInvalidField: (
    key: string,
    value?: { raw: string; error: string },
  ) => void;
  generation: number;
  past: Snapshot[];
  future: Snapshot[];
  clipboard: Snapshot | null;
  load: (definition: Definition) => void;
  changeNodes: (changes: NodeChange<EditorNode>[]) => void;
  changeEdges: (changes: EdgeChange[]) => void;
  updateNode: (id: string, data: Partial<EditorNode["data"]>) => void;
  add: (node: GraphNode) => void;
  connect: (edge: Edge) => void;
  checkpoint: () => void;
  undo: () => void;
  redo: () => void;
  copy: () => void;
  paste: () => void;
  duplicate: (id: string) => void;
  deleteNode: (id: string) => void;
};
const snapshot = (state: Snapshot): Snapshot =>
  structuredClone({ nodes: state.nodes, edges: state.edges });
const past = (state: State) => [...state.past.slice(-49), snapshot(state)];
const asNode = (node: GraphNode): EditorNode => ({
  id: node.id,
  type: "workflow",
  position: node.position,
  data: {
    kind: node.type,
    label: node.label,
    alias: node.alias || "",
    config: node.config,
  },
});
export const useEditor = create<State>((set, get) => ({
  invalidFields: {},
  setInvalidField: (key, value) =>
    set((s) => {
      const invalidFields = { ...s.invalidFields };
      if (value) invalidFields[key] = value;
      else delete invalidFields[key];
      return { invalidFields };
    }),
  nodes: [],
  edges: [],
  generation: 0,
  past: [],
  future: [],
  clipboard: null,
  load: (definition) =>
    set({
      nodes: definition.nodes.map(asNode),
      edges: definition.edges.map((e) => ({ ...e, type: "smoothstep" })),
      generation: 0,
      past: [],
      future: [],
      invalidFields: {},
    }),
  checkpoint: () => set((s) => ({ past: past(s), future: [] })),
  changeNodes: (changes) =>
    set((s) => ({
      nodes: applyNodeChanges(changes, s.nodes),
      edges: s.edges.filter(
        (e) =>
          !changes.some(
            (c) =>
              c.type === "remove" && (e.source === c.id || e.target === c.id),
          ),
      ),
      ...(changes.some((c) => c.type !== "select" && c.type !== "dimensions")
        ? {
            generation: s.generation + 1,
            ...(changes.some((c) => c.type === "remove")
              ? {
                  past: past(s),
                  future: [],
                  invalidFields: Object.fromEntries(
                    Object.entries(s.invalidFields).filter(
                      ([key]) =>
                        !changes.some(
                          (c) =>
                            c.type === "remove" && key.startsWith(c.id + ":"),
                        ),
                    ),
                  ),
                }
              : {}),
          }
        : {}),
    })),
  changeEdges: (changes) =>
    set((s) => {
      const edges = applyEdgeChanges(changes, s.edges);
      const changed =
        edges.length !== s.edges.length ||
        edges.some((edge, i) => edge !== s.edges[i]);
      return {
        edges,
        ...(changed && changes.some((c) => c.type !== "select")
          ? { generation: s.generation + 1, past: past(s), future: [] }
          : {}),
      };
    }),
  updateNode: (id, data) =>
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, ...data } } : n,
      ),
      generation: s.generation + 1,
      past: past(s),
      future: [],
    })),
  add: (node) =>
    set((s) => ({
      nodes: [
        ...s.nodes.map((n) => ({ ...n, selected: false })),
        { ...asNode(node), selected: true },
      ],
      generation: s.generation + 1,
      past: past(s),
      future: [],
    })),
  connect: (edge) =>
    set((s) => ({
      edges: [...s.edges, edge],
      generation: s.generation + 1,
      past: past(s),
      future: [],
    })),
  undo: () =>
    set((s) => {
      const previous = s.past.at(-1);
      return previous
        ? {
            ...snapshot(previous),
            past: s.past.slice(0, -1),
            future: [snapshot(s), ...s.future],
            generation: s.generation + 1,
          }
        : {};
    }),
  redo: () =>
    set((s) => {
      const next = s.future[0];
      return next
        ? {
            ...snapshot(next),
            past: [...s.past, snapshot(s)],
            future: s.future.slice(1),
            generation: s.generation + 1,
          }
        : {};
    }),
  copy: () =>
    set((s) => {
      const nodes = s.nodes.filter((n) => n.selected),
        ids = new Set(nodes.map((n) => n.id));
      return {
        clipboard: snapshot({
          nodes,
          edges: s.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
        }),
      };
    }),
  paste: () =>
    set((s) => {
      if (!s.clipboard?.nodes.length) return {};
      const mapping = new Map(
        s.clipboard.nodes.map((n) => [n.id, crypto.randomUUID()]),
      );
      const nodes = s.clipboard.nodes.map((n) => ({
        ...structuredClone(n),
        id: mapping.get(n.id)!,
        position: { x: n.position.x + 40, y: n.position.y + 40 },
        selected: true,
        data: { ...structuredClone(n.data), alias: "" },
      }));
      const edges = s.clipboard.edges.map((e) => ({
        ...e,
        id: crypto.randomUUID(),
        source: mapping.get(e.source)!,
        target: mapping.get(e.target)!,
      }));
      return {
        nodes: [...s.nodes.map((n) => ({ ...n, selected: false })), ...nodes],
        edges: [...s.edges, ...edges],
        past: past(s),
        future: [],
        generation: s.generation + 1,
      };
    }),
  duplicate: (id) => {
    const node = get().nodes.find((n) => n.id === id);
    if (node) {
      set({ clipboard: snapshot({ nodes: [node], edges: [] }) });
      get().paste();
    }
  },
  deleteNode: (id) =>
    set((s) => ({
      invalidFields: Object.fromEntries(
        Object.entries(s.invalidFields).filter(
          ([key]) => !key.startsWith(id + ":"),
        ),
      ),
      nodes: s.nodes.filter((n) => n.id !== id),
      edges: s.edges.filter((e) => e.source !== id && e.target !== id),
      past: past(s),
      future: [],
      generation: s.generation + 1,
    })),
}));
export function definitionOf(state: Snapshot): Definition {
  return {
    schema_version: 1,
    nodes: state.nodes.map((n) => ({
      id: n.id,
      type: n.data.kind,
      label: n.data.label,
      alias: n.data.alias || undefined,
      position: n.position,
      config: n.data.config,
    })),
    edges: state.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle,
      targetHandle: e.targetHandle,
    })),
  };
}
export const nodeKinds = [
  {
    kind: "manual",
    name: "Manual trigger",
    group: "Triggers",
    hint: "Start when you need to",
    color: "violet",
    config: {},
  },
  {
    kind: "webhook",
    name: "Webhook",
    group: "Triggers",
    hint: "Receive an external event",
    color: "violet",
    config: {},
  },
  {
    kind: "api",
    name: "API trigger",
    group: "Triggers",
    hint: "Start with an API request",
    color: "violet",
    config: {},
  },
  {
    kind: "schedule",
    name: "Schedule",
    group: "Triggers",
    hint: "Run on a schedule",
    color: "violet",
    config: { cron: "0 9 * * *", timezone: "Asia/Kolkata" },
  },
  {
    kind: "validate",
    name: "Validate JSON",
    group: "Logic",
    hint: "Make sure data fits",
    color: "cyan",
    config: { input: "{{ trigger.body }}", schema: { type: "object" } },
  },
  {
    kind: "condition",
    name: "Condition",
    group: "Logic",
    hint: "Choose the next step",
    color: "amber",
    config: {
      left: "{{ trigger.body.total }}",
      operator: "greater",
      right: 500,
    },
  },
  {
    kind: "transform",
    name: "Transform",
    group: "Logic",
    hint: "Map and shape your data",
    color: "violet",
    config: { mapping: { body: "{{ trigger.body }}" } },
  },
  {
    kind: "set",
    name: "Set variable",
    group: "Logic",
    hint: "Keep a value for later",
    color: "violet",
    config: { mapping: { value: "{{ trigger.body }}" } },
  },
  {
    kind: "delay",
    name: "Delay",
    group: "Logic",
    hint: "Resume after a pause",
    color: "amber",
    config: { seconds: 5 },
  },
  {
    kind: "http",
    name: "HTTP request",
    group: "Actions",
    hint: "Connect to a REST API",
    color: "cyan",
    config: {
      method: "GET",
      url: "",
      headers: {},
      query: {},
      timeout: 30,
      retry: {
        max_attempts: 3,
        initial_delay: 2,
        multiplier: 2,
        max_delay: 120,
        jitter: true,
      },
    },
  },
  {
    kind: "postgres",
    name: "PostgreSQL",
    group: "Actions",
    hint: "Read or write records",
    color: "cyan",
    config: {
      mode: "read",
      query: "SELECT 1 AS connected",
      parameters: {},
      connection_id: "",
    },
  },
  {
    kind: "callback",
    name: "Callback",
    group: "Actions",
    hint: "Send the final result",
    color: "green",
    config: {
      method: "POST",
      url: "",
      body: "{{ trigger.body }}",
      timeout: 30,
    },
  },
] as const;
