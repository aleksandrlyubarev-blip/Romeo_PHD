# Romeo — product canon

Human-maintained authority for documentation. Preserve these boundaries; cite code for implementation claims.
If code and intent differ, document the gap instead of inventing implementation.

## Product thesis
We do not build a humanoid body. We put an evidence-backed inspection brain (SOP + visual agents + CAD bridge) onto a purchased mobile/manipulator platform for EMS / SMT incoming QC.

## Container contract
Repository: aleksandrlyubarev-blip/Romeo_PHD
System role: orchestration and human-in-the-loop control.
Actor: inspection coordinator or human approver.
Input: a pipeline definition, task context, model-routing choices and approval responses.
Output: pipeline execution state, worker results, telemetry and HITL approval requests.
Implemented: pipeline parsing and execution in artifacts/api-server/src/lib/pipeline-parser.ts and pipeline-executor.ts.
Implemented: model selection in artifacts/api-server/src/lib/model-routing.ts.
Implemented: human approval pause/resume and consultation UI in artifacts/romeo-phd/src/pages/consultations.tsx.
The API server, web UI and database are internal components of this logical system container.
Romeo is an orchestrator, not a vision model; model providers are External services.
System fail-closed requirement: missing inspection evidence must reach human review, never an automatic PASS.
The generic executor is not itself the Inspection Copilot evidence policy.
Not demonstrated: a complete production connection to all four inspection/CAD/capture containers.
Not demonstrated: one cross-repository evidence-pack writer or robot motion adapter.

## System flow
Camera (External) -> FlexVision Checker capture/frame QA -> Romeo task routing -> Neuron Vision observations -> Inspection Copilot SOP/evidence policy -> human review/disposition -> PASS | REWORK | HOLD | HUMAN REVIEW; Buxter optionally proposes validated CAD/rework geometry.
Romeo owns orchestration and HITL; Neuron Vision owns five visual roles; Copilot owns the deterministic SOP gate.
Buxter defaults to FreeCAD, with optional Fusion and explicit validate/printability checks.
This flow is the target integration; the five repositories do not yet prove one connected deployment.
Target: verdict plus SHA-256 evidence pack including provenance and human disposition.

## External boundary
Purchased mobile base + manipulator + camera: External hardware, not our IP.
Flex line, Technion lab and Israel Physical AI testbed: External target environments, not asserted deployments.
Robot platform drivers and the unified hardware integration are not implemented by this documentation scaffold.

## Source snapshot
Initial audit: 48da14f086a8b857ea740742d626b9fb16e52461 (2026-09-17).
Regeneration must cite the checkout being analyzed and distinguish new code from this initial audit.
Only public source code and synthetic examples may enter documentation generation.
