import { useListPipelines } from "@workspace/api-client-react";
import { motion } from "framer-motion";
import { Activity, Cpu, Network, GitBranch, ArrowUpRight, Plus, Play } from "lucide-react";
import { Card } from "@/components/ui";
import { BUXTER_ACTIVE_PHASES, BUXTER_AGENT_LANES, BUXTER_DELIVERY_SPRINTS, BUXTER_RUNTIME_GUARDS, BUXTER_SPRINT_ONE_GOALS, BUXTER_TEMPLATES } from "@/lib/buxter";
import { Link } from "wouter";

const STATUS_COLORS: Record<string, string> = {
  completed: "text-green-400 bg-green-400/10 border-green-500/30",
  running: "text-blue-400 bg-blue-400/10 border-blue-500/30",
  paused: "text-yellow-400 bg-yellow-400/10 border-yellow-500/30",
  failed: "text-red-400 bg-red-400/10 border-red-500/30",
  pending: "text-gray-400 bg-gray-400/10 border-gray-500/30",
};

export default function Dashboard() {
  const { data: pipelines, isLoading } = useListPipelines();

  const totalPipelines = pipelines?.length ?? 0;
  const running = pipelines?.filter(p => p.status === "running").length ?? 0;
  const completed = pipelines?.filter(p => p.status === "completed").length ?? 0;
  const paused = pipelines?.filter(p => p.status === "paused").length ?? 0;

  const stats = [
    {
      title: "Total Pipelines",
      value: totalPipelines.toString(),
      icon: GitBranch,
      color: "text-primary",
      bg: "bg-primary/10",
      trend: "Across all workspaces",
    },
    {
      title: "Active Executions",
      value: running.toString(),
      icon: Activity,
      color: "text-emerald-400",
      bg: "bg-emerald-400/10",
      trend: running > 0 ? "Processing nodes..." : "All systems nominal",
    },
    {
      title: "Completed",
      value: completed.toString(),
      icon: Cpu,
      color: "text-blue-400",
      bg: "bg-blue-400/10",
      trend: "Successfully resolved",
    },
    {
      title: "Awaiting Review",
      value: paused.toString(),
      icon: Network,
      color: "text-yellow-400",
      bg: "bg-yellow-400/10",
      trend: paused > 0 ? "HITL intervention needed" : "No pending reviews",
    },
  ];

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground">Mission Control</h1>
          <p className="text-muted-foreground mt-2 font-mono text-sm">
            Romeo PHD v6.0 — Agent Development Platform. System status is{" "}
            <span className="text-green-400">GREEN</span>.
          </p>
        </div>
        <Link href="/ide">
          <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors">
            <Plus className="w-4 h-4" />
            New Pipeline
          </button>
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat, i) => (
          <motion.div
            key={stat.title}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
          >
            <Card className="p-6 relative overflow-hidden group hover:border-primary/50 transition-colors duration-300">
              <div className="absolute inset-0 bg-gradient-to-br from-white/[0.02] to-transparent pointer-events-none" />
              <div className="flex justify-between items-start mb-4">
                <div className={`p-3 rounded-xl ${stat.bg}`}>
                  <stat.icon className={`w-6 h-6 ${stat.color}`} />
                </div>
              </div>
              <div>
                <h3 className="text-muted-foreground font-medium text-sm">{stat.title}</h3>
                <div className="text-3xl font-display font-bold mt-1 text-foreground">
                  {isLoading ? "..." : stat.value}
                </div>
                <p className="text-xs text-muted-foreground mt-2 font-mono">{stat.trend}</p>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card className="p-6 border-primary/20 bg-gradient-to-br from-primary/10 via-background to-background">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-3xl space-y-3">
                <div className="inline-flex items-center rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-mono text-primary">
                  BUXTER / autonomous CAD MAS
                </div>
                <div>
                  <h2 className="text-2xl font-display font-semibold">Buxter — сквозное CAD-проектирование</h2>
                  <p className="mt-2 text-sm text-muted-foreground font-mono leading-6">
                    Архитектурный blueprint для мультиагентной системы, которая проводит изделие через
                    параметрическое 3D-моделирование, 2D-документацию, интероперабельность DWG и GUI-автоматизацию SolidWorks.
                  </p>
                </div>
              </div>
              <div className="grid gap-3 text-sm font-mono text-muted-foreground lg:min-w-[280px]">
                <div className="rounded-xl border border-border/60 bg-background/70 p-4">
                  <div className="mb-1 text-xs uppercase tracking-[0.2em] text-primary">Callsign</div>
                  <div className="text-base font-semibold text-foreground">buxter</div>
                </div>
                <div className="rounded-xl border border-border/60 bg-background/70 p-4">
                  <div className="mb-1 text-xs uppercase tracking-[0.2em] text-primary">Target flow</div>
                  <div className="text-base font-semibold text-foreground">Sprint 1 → Foundation / Sprint 2 → CAD execution / Sprint 3 → Guarded automation</div>
                </div>
              </div>
            </div>

            <div className="mt-6 grid gap-4 xl:grid-cols-3">
              {BUXTER_AGENT_LANES.map((lane) => (
                <div key={lane.title} className="rounded-xl border border-border/60 bg-background/60 p-4">
                  <div className="text-xs uppercase tracking-[0.24em] text-primary font-mono">{lane.title}</div>
                  <div className="mt-3 space-y-2">
                    {lane.agents.map((agent) => (
                      <div key={agent} className="rounded-lg border border-border/60 bg-background/70 px-3 py-2 text-sm font-medium text-foreground">
                        {agent}
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-xs leading-5 text-muted-foreground font-mono">{lane.detail}</p>
                </div>
              ))}
            </div>

            <div className="mt-6 rounded-xl border border-border/60 bg-background/60 p-4">
              <div className="text-xs uppercase tracking-[0.24em] text-primary font-mono">Runtime guards</div>
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                {BUXTER_RUNTIME_GUARDS.map((guard) => (
                  <div key={guard} className="rounded-lg border border-border/60 bg-background/70 px-3 py-3 text-xs leading-5 text-muted-foreground font-mono">
                    {guard}
                  </div>
                ))}
              </div>
            </div>
          </Card>

          <Card className="p-6 border-primary/20">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-display font-semibold">Sprint 1 Review</h2>
                <p className="mt-1 text-xs font-mono text-muted-foreground">Foundation phase закрыта; её handoff теперь служит входом для активного Sprint 2.</p>
              </div>
              <span className="rounded-full border border-primary/30 bg-primary/10 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-primary font-mono">
                {BUXTER_TEMPLATES[0].status}
              </span>
            </div>
            <div className="mt-5 grid gap-3 md:grid-cols-2">
              {BUXTER_SPRINT_ONE_GOALS.map((goal) => (
                <div key={goal} className="rounded-xl border border-border/60 bg-background/60 p-4 text-xs leading-5 font-mono text-muted-foreground">
                  {goal}
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-6 border-primary/20">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-display font-semibold">Sprint 2 Review</h2>
                <p className="mt-1 text-xs font-mono text-muted-foreground">Execution layer закрыт; его package теперь служит входом для активного Sprint 3 automation stage.</p>
              </div>
              <span className="rounded-full border border-primary/30 bg-primary/10 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-primary font-mono">
                {BUXTER_TEMPLATES[1].status}
              </span>
            </div>
            <div className="mt-5 grid gap-3 md:grid-cols-2">
              {BUXTER_TEMPLATES[1].deliverables.map((deliverable) => (
                <div key={deliverable} className="rounded-xl border border-border/60 bg-background/60 p-4 text-xs leading-5 font-mono text-muted-foreground">
                  {deliverable}
                </div>
              ))}
            </div>
            <div className="mt-5 grid gap-3 lg:grid-cols-2">
              <div className="rounded-xl border border-border/60 bg-background/60 p-4">
                <div className="text-[10px] uppercase tracking-[0.2em] text-primary font-mono">Tooling</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {BUXTER_TEMPLATES[1].tooling.map((tool) => (
                    <span key={tool} className="rounded-full border border-border/60 bg-background/70 px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground font-mono">
                      {tool}
                    </span>
                  ))}
                </div>
              </div>
              <div className="rounded-xl border border-border/60 bg-background/60 p-4">
                <div className="text-[10px] uppercase tracking-[0.2em] text-primary font-mono">Execution gates</div>
                <div className="mt-3 space-y-2">
                  {BUXTER_TEMPLATES[1].qualityGates.map((gate) => (
                    <div key={gate} className="text-xs leading-5 font-mono text-muted-foreground">• {gate}</div>
                  ))}
                </div>
              </div>
            </div>
            <p className="mt-5 text-xs leading-5 font-mono text-muted-foreground">Handoff: {BUXTER_TEMPLATES[1].handoff}</p>
          </Card>

          <Card className="p-6 border-primary/20">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-display font-semibold">Sprint 3 Scope</h2>
                <p className="mt-1 text-xs font-mono text-muted-foreground">Активный инженерный инкремент: guarded automation layer before full MAS rollout.</p>
              </div>
              <span className="rounded-full border border-primary/30 bg-primary/10 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-primary font-mono">
                {BUXTER_TEMPLATES[2].badge}
              </span>
            </div>
            <div className="mt-5 grid gap-3 md:grid-cols-2">
              {BUXTER_TEMPLATES[2].deliverables.map((deliverable) => (
                <div key={deliverable} className="rounded-xl border border-border/60 bg-background/60 p-4 text-xs leading-5 font-mono text-muted-foreground">
                  {deliverable}
                </div>
              ))}
            </div>
            <div className="mt-5 grid gap-3 lg:grid-cols-2">
              <div className="rounded-xl border border-border/60 bg-background/60 p-4">
                <div className="text-[10px] uppercase tracking-[0.2em] text-primary font-mono">Tooling</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {BUXTER_TEMPLATES[2].tooling.map((tool) => (
                    <span key={tool} className="rounded-full border border-border/60 bg-background/70 px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground font-mono">
                      {tool}
                    </span>
                  ))}
                </div>
              </div>
              <div className="rounded-xl border border-border/60 bg-background/60 p-4">
                <div className="text-[10px] uppercase tracking-[0.2em] text-primary font-mono">Automation gates</div>
                <div className="mt-3 space-y-2">
                  {BUXTER_TEMPLATES[2].qualityGates.map((gate) => (
                    <div key={gate} className="text-xs leading-5 font-mono text-muted-foreground">• {gate}</div>
                  ))}
                </div>
              </div>
            </div>
            <p className="mt-5 text-xs leading-5 font-mono text-muted-foreground">Handoff: {BUXTER_TEMPLATES[2].handoff}</p>
          </Card>

          <Card className="p-6">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-display font-semibold">Pipeline Registry</h2>
              <Link href="/ide" className="text-sm text-primary hover:underline flex items-center font-mono">
                New Pipeline <ArrowUpRight className="w-4 h-4 ml-1" />
              </Link>
            </div>
            <div className="space-y-3">
              {isLoading ? (
                <div className="animate-pulse space-y-3">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="h-16 bg-secondary/50 rounded-lg" />
                  ))}
                </div>
              ) : pipelines?.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground font-mono text-sm">
                  <GitBranch className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  No pipelines yet. Create your first one in the IDE.
                </div>
              ) : (
                pipelines?.slice(0, 8).map(pipeline => (
                  <div
                    key={pipeline.id}
                    className="flex items-center justify-between p-4 rounded-lg bg-secondary/30 border border-border/50 hover:bg-secondary/50 transition-colors"
                  >
                    <div className="flex items-center gap-4 flex-1 min-w-0">
                      <div className="flex-1 min-w-0">
                        <h4 className="font-semibold text-sm truncate">{pipeline.name}</h4>
                        <p className="text-xs text-muted-foreground font-mono mt-0.5">
                          {pipeline.resolvedCount}/{pipeline.nodeCount} nodes resolved
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 ml-4">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-mono border ${STATUS_COLORS[pipeline.status] ?? STATUS_COLORS.pending}`}
                      >
                        {pipeline.status.toUpperCase()}
                      </span>
                      <Link href={`/ide/${pipeline.id}`}>
                        <button className="p-1.5 rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors">
                          <Play className="w-3.5 h-3.5" />
                        </button>
                      </Link>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="p-6">
            <h2 className="text-xl font-display font-semibold">Buxter delivery by sprints</h2>
            <p className="mt-2 text-xs font-mono text-muted-foreground leading-5">
              Да — разработка разбита по спринтам: сначала foundation, потом executable CAD, затем GUI automation и production review loops.
            </p>
            <div className="mt-5 space-y-3">
              {BUXTER_DELIVERY_SPRINTS.map((sprint) => (
                <div key={sprint.id} className="rounded-xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-semibold text-sm text-foreground">{sprint.title}</div>
                    <span className="rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.2em] text-primary font-mono">
                      {sprint.status}
                    </span>
                  </div>
                  <p className="mt-2 text-xs font-mono leading-5 text-muted-foreground">{sprint.scope}</p>
                </div>
              ))}
            </div>
            <div className="mt-5 rounded-xl border border-border/60 bg-background/60 p-4">
              <div className="text-[10px] uppercase tracking-[0.2em] text-primary font-mono">Active sprint phases</div>
              <div className="mt-3 space-y-2">
                {BUXTER_ACTIVE_PHASES.map((phase) => (
                  <div key={phase.title} className="flex items-center justify-between gap-3 rounded-lg border border-border/60 bg-background/70 px-3 py-2">
                    <span className="text-xs font-semibold text-foreground">{phase.title}</span>
                    <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground font-mono">{phase.owner}</span>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          <Card className="p-6 relative overflow-hidden">
            <div className="absolute inset-0 bg-[url('/images/dashboard-bg.png')] bg-cover bg-center opacity-10 mix-blend-screen pointer-events-none" />
            <div className="relative z-10">
              <h2 className="text-xl font-display font-semibold mb-6">Quick Actions</h2>
              <div className="space-y-3">
                {[
                  { label: "Open IDE", desc: "Load and edit the active Buxter sprint workflow", href: "/ide", icon: "⚡" },
                  { label: "HITL Review", desc: "Respond to pending consultations", href: "/consultations", icon: "👁" },
                  { label: "Telemetry", desc: "View AI chain-of-reasoning logs", href: "/telemetry", icon: "📡" },
                ].map((action) => (
                  <Link key={action.href} href={action.href}>
                    <div className="p-4 rounded-lg bg-background/50 backdrop-blur-md border border-border/50 hover:border-primary/50 hover:bg-primary/5 transition-all cursor-pointer group">
                      <div className="flex items-center gap-3">
                        <span className="text-xl">{action.icon}</span>
                        <div>
                          <p className="font-semibold text-sm group-hover:text-primary transition-colors">
                            {action.label}
                          </p>
                          <p className="text-xs text-muted-foreground font-mono">{action.desc}</p>
                        </div>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
