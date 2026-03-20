import React, { useEffect, useState, useRef } from "react";
import { useLocation, useParams } from "wouter";
import Editor from "@monaco-editor/react";
import { ReactFlow, Background, Controls, MiniMap, useNodesState, useEdgesState, MarkerType, Handle, Position, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCreatePipeline, useGetPipeline, useExecutePipeline, type PipelineNode } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { Play, RotateCcw, Activity, SquareTerminal, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const DEFAULT_YAML = `name: Data Processing Pipeline
description: Extract, transform, validate and output data

nodes:
  - id: extract_data
    name: Extract Data
    type: data_extraction
    prompt: "Extract and identify key data points from the provided context. Return structured JSON with field names and values."

  - id: validate_schema
    name: Validate Schema
    type: validation
    depends_on: [extract_data]
    prompt: "Validate the extracted data against expected schema requirements. Check for completeness, type correctness, and business rules."

  - id: transform_data
    name: Transform Data
    type: transformation
    depends_on: [validate_schema]
    prompt: "Transform the validated data into the target output format. Apply normalization, enrichment, and formatting rules."

  - id: quality_check
    name: Quality Check
    type: analysis
    depends_on: [transform_data]
    prompt: "Perform final quality assessment. Score data completeness, accuracy, and confidence level."

  - id: generate_output
    name: Generate Output
    type: output
    depends_on: [quality_check]
    prompt: "Compile final output report with all processed data and quality metrics."`;

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
  
  const [yamlContent, setYamlContent] = useState(DEFAULT_YAML);
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
  }, [pipeline]);

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
    setYamlContent(DEFAULT_YAML);
    setNodes([]);
    setEdges([]);
    setLocation('/ide');
  };

  return (
    <div className="flex flex-col h-[calc(100vh-2rem)] rounded-xl border border-border overflow-hidden bg-background/80 backdrop-blur-sm shadow-2xl mx-4 my-4">
      {/* Top Bar */}
      <div className="h-14 border-b border-border bg-card/50 flex items-center justify-between px-4">
        <div className="flex items-center space-x-3">
          <SquareTerminal className="w-5 h-5 text-primary" />
          <span className="font-display font-semibold">
            {pipeline ? pipeline.name : "New Pipeline"}
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
      </div>

      {/* Split Screen Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel: Monaco Editor */}
        <div className="w-[40%] border-r border-border h-full flex flex-col">
          <div className="h-10 bg-secondary/30 border-b border-border/50 flex items-center px-4">
            <span className="text-xs font-mono text-muted-foreground">pipeline.yaml</span>
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
            RESET
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
