import { beforeEach, describe, expect, it } from "vitest";
import { definitionOf, useEditor } from "./editor";
import type { Definition } from "./types";

const first = crypto.randomUUID(),
  second = crypto.randomUUID();
const definition: Definition = {
  schema_version: 1,
  nodes: [
    {
      id: first,
      type: "manual",
      label: "Start",
      position: { x: 0, y: 0 },
      config: {},
    },
    {
      id: second,
      type: "transform",
      label: "Map",
      alias: "mapped",
      position: { x: 0, y: 160 },
      config: { mapping: { body: "{{ trigger.body }}" } },
    },
  ],
  edges: [
    {
      id: crypto.randomUUID(),
      source: first,
      target: second,
      sourceHandle: "success",
    },
  ],
};
describe("draft editor", () => {
  beforeEach(() => useEditor.getState().load(definition));
  it("unfinished JSON stays outside exported graphs and clears when its node is deleted", () => {
    useEditor.getState().setInvalidField(second + ":Field mapping", {
      raw: "{",
      error: "Unfinished JSON",
    });
    expect(definitionOf(useEditor.getState())).toEqual(definition);
    useEditor.getState().deleteNode(second);
    expect(useEditor.getState().invalidFields).toEqual({});
  });
  it("deleting a node removes dangling edges and undo restores both", () => {
    useEditor.getState().deleteNode(second);
    expect(useEditor.getState().edges).toHaveLength(0);
    useEditor.getState().undo();
    expect(definitionOf(useEditor.getState())).toEqual(definition);
    useEditor.getState().redo();
    expect(useEditor.getState().nodes).toHaveLength(1);
  });
  it("keyboard deletion is one atomic history entry for a node and its edges", () => {
    useEditor
      .getState()
      .setInvalidField(second + ":Field mapping", {
        raw: "{",
        error: "Unfinished JSON",
      });
    useEditor.getState().changeNodes([{ type: "remove", id: second }]);
    useEditor
      .getState()
      .changeEdges([{ type: "remove", id: definition.edges[0].id }]);
    expect(useEditor.getState().past).toHaveLength(1);
    expect(useEditor.getState().invalidFields).toEqual({});
    useEditor.getState().undo();
    expect(definitionOf(useEditor.getState())).toEqual(definition);
  });
  it("copy/paste creates new stable IDs and does not duplicate aliases", () => {
    useEditor.getState().changeNodes([
      { type: "select", id: first, selected: true },
      { type: "select", id: second, selected: true },
    ]);
    useEditor.getState().copy();
    useEditor.getState().paste();
    const data = definitionOf(useEditor.getState());
    expect(new Set(data.nodes.map((n) => n.id)).size).toBe(4);
    expect(data.edges).toHaveLength(2);
    expect(data.nodes[3].alias).toBeUndefined();
    expect(data.edges[1].source).toBe(data.nodes[2].id);
  });
  it("selection never dirties the graph and updates preserve snapshot history", () => {
    useEditor
      .getState()
      .changeNodes([{ type: "select", id: first, selected: true }]);
    expect(useEditor.getState().generation).toBe(0);
    useEditor
      .getState()
      .updateNode(second, { config: { mapping: { changed: true } } });
    useEditor.getState().undo();
    expect(useEditor.getState().nodes[1].data.config).toEqual(
      definition.nodes[1].config,
    );
  });
});
