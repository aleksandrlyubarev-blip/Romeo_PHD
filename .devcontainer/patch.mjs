/**
 * patch.mjs — автоматически исправляет критические баги перед запуском.
 *
 * Bug 1: resume route — обновляет ВСЕ узлы вместо одного (отсутствует фильтр по nodeId)
 * Bug 2: consultation respond — та же проблема с фильтром
 * Bug 3: Anthropic client — падает если нет AI_INTEGRATIONS_* переменных
 */

import { readFileSync, writeFileSync } from "fs";

let patched = 0;

function patch(filePath, from, to, label) {
  let src = readFileSync(filePath, "utf-8");
  if (src.includes(to.trim().slice(0, 60))) {
    console.log(`  ✓ Already patched: ${label}`);
    return;
  }
  if (!src.includes(from.trim().slice(0, 60))) {
    console.log(`  ⚠ Pattern not found (skipping): ${label}`);
    return;
  }
  writeFileSync(filePath, src.replace(from, to), "utf-8");
  console.log(`  ✓ Patched: ${label}`);
  patched++;
}

// ─── Bug 1 + 2: pipeline routes ──────────────────────────────
const routePath = "artifacts/api-server/src/routes/pipeline/index.ts";

// Add `and, inArray` to the drizzle-orm import
patch(
  routePath,
  `import { eq } from "drizzle-orm";`,
  `import { eq, and, inArray } from "drizzle-orm";`,
  "drizzle-orm: add and + inArray imports"
);

// Bug 1: resume route — find the paused node by status, then update only it
patch(
  routePath,
  `  // Find the node and update it based on decision
  const [node] = await db
    .select()
    .from(pipelineNodes)
    .where(
      eq(pipelineNodes.pipelineId, params.data.id),
    );

  if (body.data.decision === "approve") {
    // Mark the node as RESOLVED and update the consultation
    await db
      .update(pipelineNodes)
      .set({ status: "RESOLVED", output: body.data.feedback ?? "Approved by operator" })
      .where(
        eq(pipelineNodes.pipelineId, params.data.id)
      );`,
  `  // Find the specific paused node (AMBIGUOUS or NEEDS_CLARIFICATION)
  const [node] = await db
    .select()
    .from(pipelineNodes)
    .where(
      and(
        eq(pipelineNodes.pipelineId, params.data.id),
        inArray(pipelineNodes.status, ["AMBIGUOUS", "NEEDS_CLARIFICATION"])
      )
    )
    .orderBy(pipelineNodes.id)
    .limit(1);

  if (body.data.decision === "approve") {
    // Mark only THIS node as RESOLVED
    await db
      .update(pipelineNodes)
      .set({ status: "RESOLVED", output: body.data.feedback ?? "Approved by operator" })
      .where(eq(pipelineNodes.id, node.id));`,
  "Bug 1: resume — filter by specific node id"
);

// Also fix the reject branch in resume
patch(
  routePath,
  `  } else {
    await db
      .update(pipelineNodes)
      .set({ status: "NEEDS_CLARIFICATION" })
      .where(eq(pipelineNodes.pipelineId, params.data.id));`,
  `  } else {
    await db
      .update(pipelineNodes)
      .set({ status: "NEEDS_CLARIFICATION" })
      .where(eq(pipelineNodes.id, node.id));`,
  "Bug 1b: resume reject — filter by specific node id"
);

// Bug 2: consultation respond — use nodeId from consultation row
patch(
  routePath,
  `  // Update the node status accordingly
  const nodeStatus = body.data.decision === "approve" ? "RESOLVED" : "NEEDS_CLARIFICATION";
  await db
    .update(pipelineNodes)
    .set({
      status: nodeStatus,
      output: body.data.feedback ?? (body.data.decision === "approve" ? "Approved by operator" : "Rejected by operator"),
      executedAt: new Date(),
    })
    .where(
      eq(pipelineNodes.pipelineId, consultation.pipelineId),
    );`,
  `  // Update only the specific node referenced by the consultation
  const nodeStatus = body.data.decision === "approve" ? "RESOLVED" : "NEEDS_CLARIFICATION";
  await db
    .update(pipelineNodes)
    .set({
      status: nodeStatus,
      output: body.data.feedback ?? (body.data.decision === "approve" ? "Approved by operator" : "Rejected by operator"),
      executedAt: new Date(),
    })
    .where(
      and(
        eq(pipelineNodes.pipelineId, consultation.pipelineId),
        eq(pipelineNodes.nodeId, consultation.nodeId)
      )
    );`,
  "Bug 2: consultation respond — filter by nodeId"
);

// ─── Bug 3: Anthropic client ─────────────────────────────────
const clientPath = "lib/integrations-anthropic-ai/src/client.ts";

patch(
  clientPath,
  `if (!process.env.AI_INTEGRATIONS_ANTHROPIC_BASE_URL) {
  throw new Error(
    "AI_INTEGRATIONS_ANTHROPIC_BASE_URL must be set. Did you forget to provision the Anthropic AI integration?",
  );
}

if (!process.env.AI_INTEGRATIONS_ANTHROPIC_API_KEY) {
  throw new Error(
    "AI_INTEGRATIONS_ANTHROPIC_API_KEY must be set. Did you forget to provision the Anthropic AI integration?",
  );
}

export const anthropic = new Anthropic({
  apiKey: process.env.AI_INTEGRATIONS_ANTHROPIC_API_KEY,
  baseURL: process.env.AI_INTEGRATIONS_ANTHROPIC_BASE_URL,
});`,
  `// Support both Replit-provisioned vars and standard ANTHROPIC_API_KEY
const apiKey =
  process.env.AI_INTEGRATIONS_ANTHROPIC_API_KEY ??
  process.env.ANTHROPIC_API_KEY;

if (!apiKey) {
  throw new Error(
    "ANTHROPIC_API_KEY is required. " +
    "Add it to GitHub Codespaces Secrets or your .env file. " +
    "Get a key at https://console.anthropic.com"
  );
}

export const anthropic = new Anthropic({
  apiKey,
  // baseURL is optional — only set when using Replit Anthropic integration
  ...(process.env.AI_INTEGRATIONS_ANTHROPIC_BASE_URL
    ? { baseURL: process.env.AI_INTEGRATIONS_ANTHROPIC_BASE_URL }
    : {}),
});`,
  "Bug 3: Anthropic client — accept ANTHROPIC_API_KEY as fallback"
);

// ─── Bug 4: DB schema barrel ─────────────────────────────────
const schemaIndexPath = "lib/db/src/schema/index.ts";
patch(
  schemaIndexPath,
  `export * from "./pipelines";`,
  `export * from "./pipelines";
export * from "./agents";
export * from "./conversations";
export * from "./messages";`,
  "Bug 4: schema/index.ts — export all tables"
);

console.log(`\n  Total patched: ${patched} file(s)`);
