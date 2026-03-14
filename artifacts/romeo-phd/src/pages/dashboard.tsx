import { useListPipelines } from "@workspace/api-client-react";
import { motion } from "framer-motion";
import { Activity, Cpu, Network, GitBranch, ArrowUpRight, Plus, Play } from "lucide-react";
import { Card } from "@/components/ui";
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
        <div className="lg:col-span-2">
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

        <Card className="p-6 relative overflow-hidden">
          <div className="absolute inset-0 bg-[url('/images/dashboard-bg.png')] bg-cover bg-center opacity-10 mix-blend-screen pointer-events-none" />
          <div className="relative z-10">
            <h2 className="text-xl font-display font-semibold mb-6">Quick Actions</h2>
            <div className="space-y-3">
              {[
                { label: "Open IDE", desc: "Define a new pipeline in YAML", href: "/ide", icon: "⚡" },
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
  );
}
