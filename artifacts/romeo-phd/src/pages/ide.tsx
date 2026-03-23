import React, { useEffect, useState, useRef } from "react";
import { useLocation, useParams } from "wouter";
import Editor from "@monaco-editor/react";
import { ReactFlow, Background, Controls, MiniMap, useNodesState, useEdgesState, MarkerType, Handle, Position, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCreatePipeline, useGetPipeline, useExecutePipeline, type PipelineNode } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Play, RotateCcw, Activity, SquareTerminal, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { BUXTER_DEFAULT_TEMPLATE, BUXTER_DELIVERY_SPRINTS, BUXTER_TEMPLATES, detectBuxterTemplateId, getBuxterTemplate } from "@/lib/buxter";

// Custom node component matching status
const CustomNode = ({ data }: { data: any }) => {
  const getBorderColor = (status: string) => {
    switch(status) {
      case 'RESOLVED': return 'border-green-500 bg-green-950/40 text-green-300';
      case 'PENDING': return 'border-gray-500 bg-gray-900/50 text-gray-300';
      case 'NEEDS_CLARIFICATION': return 'border-red-500 bg-red-950/40 text-red-300';
      case 'AMBIGUOUS': return 'border-yellow-500 bg-yellow-950/40 text-yellow-300';
      default: return 'border-primary bg-background text-foreground';
    }
  };

  const getStatusIcon = (status: string) => {
    switch(status) {
      case 'RESOLVED': return '✓';
      case 'PENDING': return '⟳';
      case 'NEEDS_CLARIFICATION': return '✗';
      case 'AMBIGUOUS': return '?';
      default: return '·';
    }
  };

  return (
    <div className={`px-4 py-3 rounded-lg border-2 min-w-[200px] font-mono shadow-xl transition-all duration-300 ${getBorderColor(data.status)}`}>
      <Handle type="target" position={Position.Top} className="w-2 h-2 bg-muted-foreground" />
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs opacity-70 truncate max-w-[120px]" title={data.type}>{data.type}</span>
        <span className="font-bold">{getStatusIcon(data.status)}</span>
      </div>
      <div className="font-medium text-sm truncate">{data.name}</div>
      {data.confidenceScore && (
        <div className="text-[10px] mt-2 opacity-80 flex justify-between">
          <span>Confidence:</span>
          <span>{(data.confidenceScore * 100).toFixed(0)}%</span>
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="w-2 h-2 bg-muted-foreground" />
    </div>
  );
};

type PipelineFlowNodeData = {
  name: string;
  type: string;
  status: PipelineNode["status"];
  confidenceScore: PipelineNode["confidenceScore"];
  originalNode: PipelineNode;
};

type PipelineFlowNode = Node<PipelineFlowNodeData, "custom">;
type PipelineFlowEdge = Edge;

const nodeTypes = {
  custom: CustomNode,
};

export default function IDE() {
  const params = useParams();
  const [, setLocation] = useLocation();
  const pipelineId = params.pipelineId ? parseInt(params.pipelineId) : null;
  
  const [activeTemplateId, setActiveTemplateId] = useState(BUXTER_DEFAULT_TEMPLATE.id);
  const activeTemplate = getBuxterTemplate(activeTemplateId);
  const [yamlContent, setYamlContent] = useState(BUXTER_DEFAULT_TEMPLATE.yaml);
  const [nodes, setNodes, onNodesChange] = useNodesState<PipelineFlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<PipelineFlowEdge>([]);
  const [isRunning, setIsRunning] = useState(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { data: pipeline, refetch: refetchPipeline } = useGetPipeline(pipelineId ?? 0);

  const createPipelineMutation = useCreatePipeline();
  const executePipelineMutation = useExecutePipeline();

  // Initialize from pipeline data or update live
  useEffect(() => {
    if (pipeline) {
      if (!yamlContent || pipeline.yamlContent !== yamlContent) {
        setYamlContent(pipeline.yamlContent);
      }

      const detectedTemplateId = detectBuxterTemplateId(pipeline.yamlContent);
      if (detectedTemplateId && detectedTemplateId !== activeTemplateId) {
        setActiveTemplateId(detectedTemplateId);
      }
      
      if (pipeline.nodes && pipeline.nodes.length > 0) {
        const flowNodes: PipelineFlowNode[] = pipeline.nodes.map((n) => ({
          id: n.nodeId,
          type: "custom",
          position: { x: n.positionX, y: n.positionY },
          data: {
            name: n.name,
            type: n.type,
            status: n.status,
            confidenceScore: n.confidenceScore,
            originalNode: n
          }
        }));
        
        const flowEdges: PipelineFlowEdge[] = [];
        pipeline.nodes.forEach(n => {
          if (n.dependencies && n.dependencies.length > 0) {
            n.dependencies.forEach(depId => {
              flowEdges.push({
                id: `e-${depId}-${n.nodeId}`,
                source: depId,
                target: n.nodeId,
                animated: n.status === 'PENDING' && pipeline.status === 'running',
                style: { stroke: 'hsl(var(--primary))' },
                markerEnd: { type: MarkerType.ArrowClosed, color: 'hsl(var(--primary))' }
              });
            });
          }
        });
        
        setNodes(flowNodes);
        setEdges(flowEdges);

        if (pipeline.status === 'running') {
          setIsRunning(true);
        } else {
          setIsRunning(false);
        }
      }
    }
  }, [activeTemplateId, pipeline, yamlContent]);

  // Polling when running
  useEffect(() => {
    if (isRunning && pipelineId) {
      pollingRef.current = setInterval(() => {
        refetchPipeline();
      }, 2000);
    } else {
      if (pollingRef.current) clearInterval(pollingRef.current);
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [isRunning, pipelineId, refetchPipeline]);

  const handleRun = async () => {
    try {
      let activePipelineId = pipelineId;
      
      // If no pipeline loaded, or YAML changed, create new
      if (!pipelineId || (pipeline && pipeline.yamlContent !== yamlContent)) {
        const newPipeline = await createPipelineMutation.mutateAsync({
          data: {
            name: yamlContent.split('\n')[0].replace('name:', '').trim() || 'New Pipeline',
            yamlContent
          }
        });
        activePipelineId = newPipeline.id;
        setLocation(`/ide/${newPipeline.id}`);
      }

      if (activePipelineId) {
        // We use fetch natively for SSE or just call the execute endpoint
        setIsRunning(true);
        await executePipelineMutation.mutateAsync({ id: activePipelineId });
        refetchPipeline();
      }
    } catch (e) {
      console.error("Failed to run pipeline", e);
      setIsRunning(false);
    }
  };

  const handleReset = () => {
    setActiveTemplateId(BUXTER_DEFAULT_TEMPLATE.id);
    setYamlContent(BUXTER_DEFAULT_TEMPLATE.yaml);
    setNodes([]);
    setEdges([]);
    setLocation('/ide');
  };

  return (
    <div className="flex flex-col h-[calc(100vh-2rem)] rounded-xl border border-border overflow-hidden bg-background/80 backdrop-blur-sm shadow-2xl mx-4 my-4">
      {/* Top Bar */}
      <div className="min-h-14 border-b border-border bg-card/50 flex items-center justify-between px-4 py-3 gap-4">
        <div className="flex items-center space-x-3 min-w-0">
          <SquareTerminal className="w-5 h-5 text-primary" />
          <span className="font-display font-semibold">
            {pipeline ? pipeline.name : activeTemplate.name}
          </span>
          {pipeline && (
            <Badge variant="outline" className={`font-mono text-xs ml-2 ${
              pipeline.status === 'running' ? 'bg-primary/20 text-primary border-primary/50' : 
              pipeline.status === 'completed' ? 'bg-green-500/20 text-green-400 border-green-500/50' :
              pipeline.status === 'paused' ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50 animate-pulse' :
              'bg-secondary text-muted-foreground'
            }`}>
              {pipeline.status.toUpperCase()}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {BUXTER_TEMPLATES.map((template) => (
              <Button
                key={template.id}
                variant={activeTemplateId === template.id ? "default" : "secondary"}
                className="font-mono text-[11px]"
                onClick={() => {
                  setActiveTemplateId(template.id);
                  setYamlContent(template.yaml);
                }}
              >
                {template.badge}
              </Button>
            ))}
            <Badge variant="outline" className="font-mono text-[10px] uppercase tracking-[0.2em]">Sprint-driven CAD</Badge>
          </div>
        </div>
      </div>

      {/* Split Screen Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel: Monaco Editor */}
        <div className="w-[40%] border-r border-border h-full flex flex-col">
          <div className="border-b border-border/50 bg-secondary/30 px-4 py-3 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-mono text-muted-foreground">pipeline.yaml</span>
              <span className="text-[10px] uppercase tracking-[0.2em] text-primary font-mono">{activeTemplate.badge} preset</span>
            </div>
            <div className="rounded-lg border border-border/60 bg-background/60 px-3 py-3">
              <div className="text-xs font-semibold text-foreground">{activeTemplate.name}</div>
              <p className="mt-1 text-[11px] leading-5 text-muted-foreground font-mono">{activeTemplate.summary}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-primary/30 bg-primary/10 px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-primary font-mono">
                  {activeTemplate.sprint}
                </span>
                <span className="rounded-full border border-border/60 bg-background/70 px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground font-mono">
                  {activeTemplate.status}
                </span>
              </div>
              <p className="mt-3 text-[11px] leading-5 text-muted-foreground font-mono">Next focus: {activeTemplate.nextFocus}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {activeTemplate.deliverables.map((deliverable) => (
                  <span key={deliverable} className="rounded-full border border-border/60 bg-background/70 px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground font-mono">
                    {deliverable}
                  </span>
                ))}
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                <div className="rounded-lg border border-border/60 bg-background/70 px-3 py-3">
                  <div className="text-[10px] uppercase tracking-[0.2em] text-primary font-mono">Tooling</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {activeTemplate.tooling.map((tool) => (
                      <span key={tool} className="rounded-full border border-border/60 bg-background px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground font-mono">
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="rounded-lg border border-border/60 bg-background/70 px-3 py-3">
                  <div className="text-[10px] uppercase tracking-[0.2em] text-primary font-mono">Quality gates</div>
                  <div className="mt-2 space-y-2">
                    {activeTemplate.qualityGates.map((gate) => (
                      <div key={gate} className="text-[11px] leading-5 text-muted-foreground font-mono">• {gate}</div>
                    ))}
                  </div>
                </div>
              </div>
              <p className="mt-4 text-[11px] leading-5 text-muted-foreground font-mono">Handoff: {activeTemplate.handoff}</p>
            </div>
            <div className="space-y-3">
              <div className="text-[10px] uppercase tracking-[0.2em] text-primary font-mono">Current sprint phases</div>
              <div className="grid gap-3 xl:grid-cols-2">
                {activeTemplate.phases.map((phase) => (
                  <div key={phase.title} className="rounded-lg border border-border/60 bg-background/60 px-3 py-2">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs font-semibold text-foreground">{phase.title}</span>
                      <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-primary">{phase.owner}</span>
                    </div>
                    <p className="mt-1 text-[11px] leading-5 text-muted-foreground font-mono">{phase.outcome}</p>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-dashed border-border/60 bg-background/40 px-3 py-3">
              <div className="text-[10px] uppercase tracking-[0.2em] text-primary font-mono">Sprint-based delivery</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {BUXTER_DELIVERY_SPRINTS.map((sprint) => (
                  <span key={sprint.id} className="rounded-full border border-border/60 bg-background/70 px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground font-mono">
                    {sprint.title}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <div className="flex-1">
            <Editor
              height="100%"
              defaultLanguage="yaml"
              theme="vs-dark"
              value={yamlContent}
              onChange={(value) => setYamlContent(value || '')}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                fontFamily: 'JetBrains Mono',
                padding: { top: 16 },
                scrollBeyondLastLine: false,
                smoothScrolling: true,
                cursorBlinking: "smooth",
              }}
            />
          </div>
        </div>

        {/* Right Panel: React Flow Graph */}
        <div className="w-[60%] h-full relative bg-gray-950">
          <div className="absolute top-4 right-4 z-10">
            <Badge className="bg-black/50 text-muted-foreground backdrop-blur-md font-mono text-xs border-white/10">SemanticIntentGraph™</Badge>
          </div>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            fitView
            className="bg-gray-950"
            colorMode="dark"
          >
            <Background color="#333" gap={16} />
            <Controls className="bg-black/50 border-white/10 fill-white" />
            <MiniMap 
              className="bg-black/50 border-white/10" 
              maskColor="rgba(255, 255, 255, 0.1)"
              nodeColor={(node) => {
                const s = node.data?.status;
                if(s === 'RESOLVED') return '#22c55e';
                if(s === 'NEEDS_CLARIFICATION') return '#ef4444';
                if(s === 'AMBIGUOUS') return '#eab308';
                return '#6b7280';
              }} 
            />
          </ReactFlow>
        </div>
      </div>

      {/* Bottom Bar Controls */}
      <div className="h-16 border-t border-border bg-card/80 backdrop-blur-md flex items-center justify-between px-6">
        <div className="flex items-center text-sm font-mono text-muted-foreground">
          <Activity className="w-4 h-4 mr-2 text-primary" />
          System ready
        </div>
        <div className="flex items-center space-x-3">
          <Button variant="ghost" className="font-mono text-xs hover-elevate" onClick={handleReset}>
            <RotateCcw className="w-4 h-4 mr-2" />
            RESET PRESET
          </Button>
          <Button 
            className="font-mono text-xs bg-primary hover:bg-primary/90 text-primary-foreground font-bold hover-elevate active-elevate-2 min-w-[120px]"
            onClick={handleRun}
            disabled={isRunning || createPipelineMutation.isPending || executePipelineMutation.isPending}
          >
            {isRunning || createPipelineMutation.isPending || executePipelineMutation.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Play className="w-4 h-4 mr-2 fill-current" />
            )}
            {isRunning ? 'EXECUTING...' : 'RUN PIPELINE'}
          </Button>
        </div>
      </div>
    </div>
  );
}
