export type BuxterTemplateId = "buxter-sprint-1" | "buxter-sprint-2" | "buxter-sprint-3" | "buxter-full-mas";

export type BuxterTemplate = {
  id: BuxterTemplateId;
  name: string;
  badge: string;
  sprint: string;
  status: "completed" | "active" | "planned";
  nextFocus: string;
  summary: string;
  yaml: string;
  deliverables: readonly string[];
  tooling: readonly string[];
  qualityGates: readonly string[];
  phases: readonly {
    title: string;
    owner: string;
    outcome: string;
  }[];
  handoff: string;
};

export type BuxterDeliverySprint = {
  id: string;
  title: string;
  status: "completed" | "active" | "planned";
  scope: string;
};

const BUXTER_SPRINT_ONE_YAML = `name: Buxter Sprint 1 Foundation
description: Establish orchestration, FreeCAD planning, geometry gates, and export contracts for Sprint 1

nodes:
  - id: intake_requirements
    name: Intake Requirements
    type: requirements_intake
    prompt: "Normalize the engineering brief into structured requirements, constraints, acceptance criteria, and explicit unknowns for Sprint 1."

  - id: orchestrate_foundation
    name: Orchestrate Foundation
    type: orchestrator
    depends_on: [intake_requirements]
    prompt: "Build the Sprint 1 execution plan: define deterministic steps, tool routing, rollback checkpoints, and review gates for the Buxter foundation workflow."

  - id: freecad_plan
    name: FreeCAD Modeling Plan
    type: freecad_planner
    depends_on: [orchestrate_foundation]
    prompt: "Produce the FreeCAD modeling plan with parametric features, editable dimensions, reference geometry, and implementation priorities."

  - id: geometry_gate
    name: Geometry Quality Gate
    type: geometry_validator
    depends_on: [freecad_plan]
    prompt: "Validate whether the proposed model strategy is safe for downstream CAD. Highlight topology risks, missing dimensions, and conditions that should block release."

  - id: export_contract
    name: Export Contract
    type: cad_interop_contract
    depends_on: [geometry_gate]
    prompt: "Define the interoperability contract for downstream STEP/DXF/DWG transfer, including required layers, dimensions, tolerances, and annotation fidelity."

  - id: sprint_review_gate
    name: Sprint Review Gate
    type: release_gate
    depends_on: [export_contract]
    prompt: "Summarize Sprint 1 deliverables, unresolved risks, readiness for Sprint 2, and the exact handoff package required for AutoCAD/SolidWorks automation."`;

const BUXTER_SPRINT_TWO_YAML = `name: Buxter Sprint 2 CAD Execution
description: Execute the first CAD-oriented path with FreeCAD, geometry validation, and export-ready interoperability

nodes:
  - id: orchestrate_execution
    name: Orchestrate Execution
    type: orchestrator
    prompt: "Translate the approved Sprint 1 handoff into an executable CAD runbook with deterministic step order, validation checkpoints, and escalation conditions."

  - id: freecad_execute
    name: FreeCAD Execute Model
    type: freecad_executor
    depends_on: [orchestrate_execution]
    prompt: "Generate the first executable FreeCAD-oriented modeling instructions, including feature order, parametric controls, and expected model outputs."

  - id: geometry_validate
    name: Validate Geometry
    type: geometry_validator
    depends_on: [freecad_execute]
    prompt: "Validate topology, dimensions, and model integrity before downstream export. Flag issues that should block CAD release."

  - id: interoperability_export
    name: Interoperability Export
    type: cad_interop
    depends_on: [geometry_validate]
    prompt: "Prepare export-ready interoperability outputs and define exact STEP/DXF/DWG handoff rules for downstream CAD systems."

  - id: execution_review_gate
    name: Execution Review Gate
    type: release_gate
    depends_on: [interoperability_export]
    prompt: "Summarize executable CAD results, residual risks, and the readiness decision for Sprint 3 automation work."`;

const BUXTER_SPRINT_THREE_YAML = `name: Buxter Sprint 3 Automation Layer
description: Add guarded CAD automation, rollback loops, and production review for the first automation stage

nodes:
  - id: orchestrate_automation
    name: Orchestrate Automation
    type: orchestrator
    prompt: "Translate the approved Sprint 2 execution package into a guarded automation runbook with safety checks, automation gates, and rollback triggers."

  - id: autocad_automation
    name: AutoCAD Automation Prep
    type: autocad_automation
    depends_on: [orchestrate_automation]
    prompt: "Prepare automated 2D documentation flow, including layer mapping, export consistency, and automation-safe drafting instructions."

  - id: solidworks_rpa_guarded
    name: SolidWorks Guarded RPA
    type: solidworks_rpa
    depends_on: [autocad_automation]
    prompt: "Drive guarded GUI automation for SolidWorks import and assembly checks, logging every decision point and anomaly for rollback review."

  - id: automation_rollback
    name: Automation Rollback Loop
    type: rollback_manager
    depends_on: [solidworks_rpa_guarded]
    prompt: "Evaluate automation failures, trigger rollback-safe recovery steps, and isolate whether the issue belongs to geometry, interoperability, or GUI execution."

  - id: production_review_gate
    name: Production Review Gate
    type: release_gate
    depends_on: [automation_rollback]
    prompt: "Summarize automation readiness, remaining safety risks, and the go/no-go handoff decision for full MAS production rollout."`;

const BUXTER_FULL_YAML = `name: Buxter End-to-End CAD MAS
description: Orchestrate FreeCAD, AutoCAD interoperability, and SolidWorks GUI validation with rollback checkpoints

nodes:
  - id: orchestrate_scope
    name: Orchestrate Scope
    type: orchestrator
    prompt: "Parse the engineering brief into deterministic requirements, success criteria, tool routing, and rollback checkpoints for the Buxter multi-agent system."

  - id: freecad_modeling
    name: FreeCAD Parametric Modeling
    type: freecad_python
    depends_on: [orchestrate_scope]
    prompt: "Use the FreeCAD Python API to generate or update the parametric 3D model, preserving editable dimensions, feature intent, and manufacturing metadata."

  - id: geometry_validation
    name: Geometry & Topology Validation
    type: geometry_validator
    depends_on: [freecad_modeling]
    prompt: "Validate manifold topology, feature consistency, collision risks, and export readiness. If geometry is unsafe for downstream CAD, emit an explicit rollback recommendation."

  - id: interoperability_export
    name: Neutral Export & Interoperability
    type: cad_interop
    depends_on: [geometry_validation]
    prompt: "Export the validated model into neutral/interoperable formats and prepare a data contract that preserves layers, dimensions, tolerances, and annotation mappings."

  - id: autocad_documentation
    name: AutoCAD DWG Documentation
    type: autocad_exchange
    depends_on: [interoperability_export]
    prompt: "Create or update annotated 2D drawing deliverables for AutoCAD/DWG, preserving dimensions, tolerances, title blocks, and layer semantics from the FreeCAD model."

  - id: solidworks_rpa_review
    name: SolidWorks GUI Review
    type: solidworks_rpa
    depends_on: [autocad_documentation]
    prompt: "Drive the SolidWorks interface via CV/RPA to import the model, create or verify mates, inspect the assembly state, and capture nondeterministic GUI failures for the orchestrator."

  - id: rollback_and_report
    name: Rollback & Final Report
    type: rollback_manager
    depends_on: [solidworks_rpa_review]
    prompt: "Evaluate all prior outputs, execute the defined rollback path when failures or ambiguities are detected, and produce the final engineering report with risk status, handoff actions, and audit logs."`;

export const BUXTER_TEMPLATES: readonly BuxterTemplate[] = [
  {
    id: "buxter-sprint-1",
    name: "Buxter Sprint 1 Foundation",
    badge: "Sprint 1",
    sprint: "Sprint 1",
    status: "completed",
    nextFocus: "Closed in review; foundation artifacts now feed Sprint 2 execution.",
    summary: "Foundation sprint for orchestration, FreeCAD planning, geometry gating, and export contracts.",
    yaml: BUXTER_SPRINT_ONE_YAML,
    deliverables: [
      "Structured requirements intake",
      "Deterministic orchestration plan",
      "FreeCAD modeling blueprint",
      "Geometry quality gate",
      "Export / interoperability contract",
      "Sprint 2 handoff package",
    ],
    tooling: ["Requirements normalizer", "Orchestrator planner", "Geometry gate"],
    qualityGates: ["Requirements resolved", "Model strategy defined", "Export contract approved"],
    phases: [
      {
        title: "Foundation intake",
        owner: "Requirements normalizer",
        outcome: "Normalize engineering inputs, constraints, and unresolved questions before CAD planning starts.",
      },
      {
        title: "Planning contract",
        owner: "Orchestrator planner",
        outcome: "Define deterministic sequencing, review checkpoints, and rollback triggers for the first CAD increment.",
      },
      {
        title: "Geometry gate",
        owner: "Geometry validator",
        outcome: "Approve the modeling strategy and export contract that become the Sprint 2 handoff package.",
      },
    ],
    handoff: "Sprint 1 closes with an approved execution contract for the first executable CAD path.",
  },
  {
    id: "buxter-sprint-2",
    name: "Buxter Sprint 2 CAD Execution",
    badge: "Sprint 2",
    sprint: "Sprint 2",
    status: "completed",
    nextFocus: "Closed in review; execution package now feeds Sprint 3 automation.",
    summary: "First executable CAD layer with FreeCAD execution, geometry validation, and export-ready interoperability.",
    yaml: BUXTER_SPRINT_TWO_YAML,
    deliverables: [
      "Executable CAD runbook",
      "FreeCAD execution stage",
      "Geometry validation gate",
      "Interoperability export package",
      "Sprint 3 automation decision",
    ],
    tooling: ["FreeCAD executor", "Geometry validator", "Interoperability exporter"],
    qualityGates: ["Executable model produced", "Geometry cleared for export", "Downstream handoff approved"],
    phases: [
      {
        title: "Execution runbook",
        owner: "Orchestrator",
        outcome: "Translate the Sprint 1 handoff into a deterministic CAD execution sequence.",
      },
      {
        title: "FreeCAD execution",
        owner: "FreeCAD executor",
        outcome: "Produce the first executable model path with controlled feature order and parameters.",
      },
      {
        title: "Interop handoff",
        owner: "Geometry + interop",
        outcome: "Validate geometry and publish the export package that seeds Sprint 3 automation.",
      },
    ],
    handoff: "Sprint 2 exits with the first executable CAD package and a go/no-go decision for Sprint 3 automation.",
  },
  {
    id: "buxter-sprint-3",
    name: "Buxter Sprint 3 Automation Layer",
    badge: "Sprint 3",
    sprint: "Sprint 3",
    status: "active",
    nextFocus: "Stabilize guarded automation before full MAS production rollout.",
    summary: "Automation-layer increment with guarded AutoCAD/SolidWorks flow, rollback loops, and production review.",
    yaml: BUXTER_SPRINT_THREE_YAML,
    deliverables: [
      "Automation runbook",
      "AutoCAD automation prep",
      "Guarded SolidWorks RPA",
      "Rollback-safe recovery loop",
      "Production review decision",
    ],
    tooling: ["AutoCAD automation", "SolidWorks RPA", "Rollback manager"],
    qualityGates: ["Automation path reproducible", "Rollback tested", "Production review approved"],
    phases: [
      {
        title: "Automation orchestration",
        owner: "Orchestrator",
        outcome: "Convert the Sprint 2 execution package into a guarded automation runbook with explicit gates.",
      },
      {
        title: "CAD automation prep",
        owner: "AutoCAD automation",
        outcome: "Prepare automation-safe drafting, mapping, and export conventions for repeatable runs.",
      },
      {
        title: "Guarded GUI execution",
        owner: "SolidWorks RPA",
        outcome: "Run supervised import and assembly checks with decision logging and anomaly capture.",
      },
      {
        title: "Rollback + production review",
        owner: "Rollback manager",
        outcome: "Exercise rollback-safe recovery and emit the go/no-go production recommendation.",
      },
    ],
    handoff: "Sprint 3 exits with a guarded automation package and a production rollout recommendation for full MAS.",
  },
  {
    id: "buxter-full-mas",
    name: "Buxter End-to-End CAD MAS",
    badge: "Full MAS",
    sprint: "Sprint 2+",
    status: "planned",
    nextFocus: "Connect real executor layers for FreeCAD, interoperability, and GUI automation.",
    summary: "Future-state end-to-end workflow for FreeCAD → AutoCAD → SolidWorks execution.",
    yaml: BUXTER_FULL_YAML,
    deliverables: [
      "FreeCAD model execution",
      "Topology validation",
      "DWG/neutral interoperability",
      "AutoCAD documentation",
      "SolidWorks RPA review",
      "Rollback and final report",
    ],
    tooling: ["FreeCAD executor", "DWG exchange", "SolidWorks RPA"],
    qualityGates: ["CAD outputs published", "GUI automation stable", "Rollback safety verified"],
    phases: [
      {
        title: "Scope orchestration",
        owner: "Orchestrator",
        outcome: "Route the end-to-end flow across modeling, interoperability, GUI review, and rollback checkpoints.",
      },
      {
        title: "Model + validate",
        owner: "FreeCAD + validator",
        outcome: "Build the parametric model and prove topology/export readiness for downstream CAD.",
      },
      {
        title: "Interop + documentation",
        owner: "DWG exchange",
        outcome: "Publish neutral exports and annotated 2D outputs for downstream CAD consumers.",
      },
      {
        title: "GUI review + report",
        owner: "SolidWorks RPA",
        outcome: "Close the governed rollout loop with GUI validation, rollback handling, and reporting.",
      },
    ],
    handoff: "Full MAS handoff targets production review and governed automation rollout.",
  },
] as const;

export const BUXTER_DEFAULT_TEMPLATE = BUXTER_TEMPLATES[2];
export const BUXTER_TEMPLATE_NAME = BUXTER_DEFAULT_TEMPLATE.name;
export const BUXTER_DEFAULT_YAML = BUXTER_DEFAULT_TEMPLATE.yaml;

export const BUXTER_DELIVERY_SPRINTS: readonly BuxterDeliverySprint[] = [
  {
    id: "sprint-1",
    title: "Sprint 1 / Foundation",
    status: "completed",
    scope: "Requirements intake, orchestration contract, geometry gate, export contract, Sprint 2 handoff.",
  },
  {
    id: "sprint-2",
    title: "Sprint 2 / CAD execution",
    status: "completed",
    scope: "Wire FreeCAD execution, downstream interoperability, and first executable CAD outputs.",
  },
  {
    id: "sprint-3",
    title: "Sprint 3 / GUI automation",
    status: "active",
    scope: "Add AutoCAD/SolidWorks automation, RPA safety boundaries, and production review loops.",
  },
] as const;

export const BUXTER_AGENT_LANES = [
  {
    title: "Оркестрация",
    agents: ["Buxter Orchestrator", "State / rollback manager"],
    detail: "Контролирует порядок шагов, retry/rollback и журнал решений на протяжении всего CAD-цикла.",
  },
  {
    title: "Open CAD",
    agents: ["FreeCAD modeling agent", "Geometry + topology validator"],
    detail: "Строит параметрическую 3D-модель, проверяет геометрию и готовит нейтральные форматы для обмена.",
  },
  {
    title: "Interop + GUI",
    agents: ["DWG interoperability agent", "SolidWorks RPA/CV agent"],
    detail: "Передаёт 2D-документацию в AutoCAD и завершает сборку/проверку через GUI-автоматизацию SolidWorks.",
  },
] as const;

export const BUXTER_RUNTIME_GUARDS = [
  "Запрет на монолитный single-LLM execution: Buxter работает как MAS с выделенными ролями.",
  "Rollback-first orchestration для ошибок импорта, сопряжений и геометрических коллизий.",
  "Полное логирование действий RPA-агента и инженерных handoff-точек для HITL-review.",
] as const;

export const BUXTER_ACTIVE_PHASES = BUXTER_DEFAULT_TEMPLATE.phases;

export const BUXTER_SPRINT_ONE_GOALS = [
  "Establish deterministic orchestration and rollback checkpoints.",
  "Prepare FreeCAD modeling plan instead of full executor runtime.",
  "Introduce geometry gate before downstream CAD release.",
  "Produce export contract and Sprint 2 handoff package.",
] as const;

export function getBuxterTemplate(templateId: BuxterTemplateId) {
  return BUXTER_TEMPLATES.find((template) => template.id === templateId) ?? BUXTER_DEFAULT_TEMPLATE;
}

export function detectBuxterTemplateId(yamlContent: string): BuxterTemplateId | null {
  const normalized = yamlContent.trim();

  const exactTemplate = BUXTER_TEMPLATES.find((template) => template.yaml.trim() === normalized);
  if (exactTemplate) {
    return exactTemplate.id;
  }

  const nameLine = normalized
    .split("\n")
    .find((line) => line.trim().toLowerCase().startsWith("name:"));

  if (!nameLine) {
    return null;
  }

  const templateName = nameLine.split(":").slice(1).join(":").trim();
  const matchedTemplate = BUXTER_TEMPLATES.find((template) => template.name === templateName);

  return matchedTemplate?.id ?? null;
}

export function getBuxterTemplateFromYaml(yamlContent: string) {
  const detectedTemplateId = detectBuxterTemplateId(yamlContent);

  return detectedTemplateId ? getBuxterTemplate(detectedTemplateId) : null;
}
