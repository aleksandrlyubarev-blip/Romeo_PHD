# @workspace/fusion-360-integrations

Thin TypeScript shim that lets the RomeoPHD `pipeline-executor` dispatch
modeling jobs to the Buxter Fusion 360 backend.

This package does **not** talk to Fusion 360 directly. It speaks to a
local Buxter HTTP wrapper (planned, see
`docs/buxter-fusion-360-integration.md`), which in turn drives Fusion in
one of three execution modes:

- `dryrun` — Buxter only emits the generated Fusion Python script and
  the operator runs it manually.
- `subprocess` — Buxter invokes the Fusion 360 binary with
  `-ExecuteScript=` on a workstation.
- `mcp` — Claude Desktop drives Fusion 360 via the official Fusion 360
  MCP connector; Buxter only ships the script as the prompt payload.

## Usage

```ts
import {
  BuxterFusionClient,
  FUSION_PIPELINE_NODE_TYPE,
} from "@workspace/fusion-360-integrations";

const client = new BuxterFusionClient({
  baseUrl: process.env.BUXTER_FUSION_BASE_URL ?? "http://localhost:8081",
  token: process.env.BUXTER_FUSION_TOKEN,
});

const result = await client.draw({
  description: "корпус для платы Pi 5 95×65×30 мм, M3 отверстия по углам",
  execMode: "dryrun",
  exportFormats: ["stl", "step"],
});

if (!result.ok) {
  throw new Error(result.stderr);
}
```

The `FUSION_PIPELINE_NODE_TYPE` constant is the canonical node type for
pipeline YAMLs that target this integration.
