import yaml from "js-yaml";

export interface ParsedNode {
  id: string;
  name: string;
  type: string;
  prompt?: string;
  dependencies: string[];
}

export interface ParsedPipeline {
  name: string;
  description?: string;
  nodes: ParsedNode[];
}

export class CyclicDependencyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CyclicDependencyError";
  }
}

export function parsePipelineYaml(yamlContent: string): ParsedPipeline {
  const raw = yaml.load(yamlContent) as Record<string, unknown>;

  if (!raw || typeof raw !== "object") {
    throw new Error("Invalid YAML: expected an object");
  }

  const name = (raw["name"] as string) ?? "Unnamed Pipeline";
  const description = raw["description"] as string | undefined;
  const rawNodes = (raw["nodes"] as Record<string, unknown>[]) ?? [];

  if (!Array.isArray(rawNodes)) {
    throw new Error("Invalid YAML: 'nodes' must be an array");
  }

  const nodes: ParsedNode[] = rawNodes.map((n) => {
    if (!n["id"]) throw new Error(`Node missing required field 'id'`);
    if (!n["name"]) throw new Error(`Node '${n["id"]}' missing required field 'name'`);

    return {
      id: String(n["id"]),
      name: String(n["name"]),
      type: String(n["type"] ?? "task"),
      prompt: n["prompt"] ? String(n["prompt"]) : undefined,
      dependencies: Array.isArray(n["depends_on"])
        ? (n["depends_on"] as string[]).map(String)
        : [],
    };
  });

  return { name, description, nodes };
}

/**
 * Kahn's Algorithm for topological sort of DAG nodes.
 * O(V + E) time complexity.
 * Throws CyclicDependencyError if a cycle is detected.
 */
export function kahnTopologicalSort(nodes: ParsedNode[]): ParsedNode[] {
  const nodeMap = new Map<string, ParsedNode>(nodes.map((n) => [n.id, n]));
  const inDegree = new Map<string, number>(nodes.map((n) => [n.id, 0]));

  // Calculate in-degrees
  for (const node of nodes) {
    for (const dep of node.dependencies) {
      if (!nodeMap.has(dep)) {
        throw new Error(`Node '${node.id}' depends on unknown node '${dep}'`);
      }
      inDegree.set(node.id, (inDegree.get(node.id) ?? 0) + 1);
    }
  }

  // Queue: all nodes with in-degree 0 (no dependencies)
  const queue: string[] = [];
  for (const [id, degree] of inDegree) {
    if (degree === 0) queue.push(id);
  }

  const sorted: ParsedNode[] = [];

  while (queue.length > 0) {
    const nodeId = queue.shift()!;
    const node = nodeMap.get(nodeId)!;
    sorted.push(node);

    // For all nodes that depend on this node, reduce their in-degree
    for (const other of nodes) {
      if (other.dependencies.includes(nodeId)) {
        const newDegree = (inDegree.get(other.id) ?? 1) - 1;
        inDegree.set(other.id, newDegree);
        if (newDegree === 0) {
          queue.push(other.id);
        }
      }
    }
  }

  // If we didn't process all nodes, there's a cycle
  if (sorted.length !== nodes.length) {
    throw new CyclicDependencyError(
      "Cyclic dependency detected in pipeline graph. Ensure nodes form a DAG."
    );
  }

  return sorted;
}

/**
 * Compute grid layout positions for nodes based on topological levels.
 */
export function computeNodePositions(
  nodes: ParsedNode[]
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();

  // Determine the "level" of each node (longest path from a root)
  const levels = new Map<string, number>(nodes.map((n) => [n.id, 0]));

  const sorted = kahnTopologicalSort(nodes);
  for (const node of sorted) {
    const currentLevel = levels.get(node.id) ?? 0;
    // All nodes that depend on this one get level + 1
    for (const other of nodes) {
      if (other.dependencies.includes(node.id)) {
        const otherLevel = levels.get(other.id) ?? 0;
        levels.set(other.id, Math.max(otherLevel, currentLevel + 1));
      }
    }
  }

  // Group nodes by level
  const byLevel = new Map<number, string[]>();
  for (const [id, level] of levels) {
    const list = byLevel.get(level) ?? [];
    list.push(id);
    byLevel.set(level, list);
  }

  const X_GAP = 280;
  const Y_GAP = 150;

  for (const [level, ids] of byLevel) {
    ids.forEach((id, i) => {
      const x = level * X_GAP + 80;
      const y = i * Y_GAP + 80 - ((ids.length - 1) * Y_GAP) / 2 + 300;
      positions.set(id, { x, y });
    });
  }

  return positions;
}
