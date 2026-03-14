import { useListTelemetryEvents } from "@workspace/api-client-react";
import { Activity, TerminalSquare } from "lucide-react";

export default function Telemetry() {
  const { data: events, isLoading } = useListTelemetryEvents(
    { limit: 100 },
    { query: { refetchInterval: 5000 } }
  );

  return (
    <div className="p-8 max-w-7xl mx-auto w-full h-full flex flex-col">
      <div className="flex items-center justify-between border-b border-border pb-6 mb-6">
        <div>
          <h1 className="text-3xl font-display font-bold tracking-tight flex items-center">
            <Activity className="w-8 h-8 mr-3 text-primary" />
            Telemetry Stream
          </h1>
          <p className="text-muted-foreground mt-1 font-mono text-sm">
            Live chain-of-reasoning events across all pipelines
          </p>
        </div>
        <div className="flex items-center">
          <span className="relative flex h-3 w-3 mr-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-primary" />
          </span>
          <span className="font-mono text-sm text-primary">LIVE</span>
        </div>
      </div>

      <div className="flex-1 bg-black rounded-lg border border-border/50 overflow-hidden flex flex-col font-mono text-sm shadow-2xl relative">
        <div className="h-10 bg-secondary/50 border-b border-white/5 flex items-center px-4">
          <TerminalSquare className="w-4 h-4 text-muted-foreground mr-2" />
          <span className="text-muted-foreground text-xs">/var/log/romeo-phd/telemetry.log</span>
          <span className="ml-auto text-xs text-muted-foreground">{events?.length ?? 0} events</span>
        </div>
        <div className="flex-1 p-4 overflow-y-auto overflow-x-auto space-y-1">
          {isLoading ? (
            <div className="text-primary/50 animate-pulse">
              Establishing secure connection to telemetry server...
            </div>
          ) : !events || events.length === 0 ? (
            <div className="text-muted-foreground">
              <span className="text-green-400">$</span> Waiting for pipeline events...
              <span className="animate-pulse">_</span>
            </div>
          ) : (
            [...events].reverse().map((event, i) => (
              <div
                key={event.id ?? i}
                className="flex gap-2 hover:bg-white/5 px-2 py-0.5 rounded transition-colors group"
              >
                <span className="text-gray-500 shrink-0 w-52">
                  [{new Date(event.createdAt).toISOString()}]
                </span>
                <span className="text-blue-400 shrink-0 w-16">
                  P-{event.pipelineId ?? "SYS"}
                </span>
                <span className="text-purple-400 shrink-0 w-32 truncate">
                  {event.nodeId ?? "SYSTEM"}
                </span>
                <span
                  className={`shrink-0 w-32 font-bold ${
                    event.eventType.includes("error") || event.eventType.includes("failed")
                      ? "text-red-400"
                      : event.eventType.includes("completed") || event.eventType.includes("resolved")
                      ? "text-green-400"
                      : event.eventType.includes("hitl") || event.eventType.includes("paused")
                      ? "text-yellow-400"
                      : "text-cyan-400"
                  }`}
                >
                  {event.eventType}
                </span>
                <span className="text-green-300 flex-1 break-all">
                  {typeof event.payload === "object"
                    ? JSON.stringify(event.payload)
                    : String(event.payload)}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
