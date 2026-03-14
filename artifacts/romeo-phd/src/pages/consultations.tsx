import { useListPipelines, useListConsultations, useRespondToConsultation, Consultation } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ShieldAlert, Check, X, Loader2 } from "lucide-react";
import { useState } from "react";
import { Textarea } from "@/components/ui/textarea";

export default function Consultations() {
  const { data: pipelines, isLoading: pipelinesLoading } = useListPipelines();
  
  const pausedPipelines = pipelines?.filter(p => p.status === 'paused') || [];

  return (
    <div className="p-8 max-w-5xl mx-auto w-full space-y-8 h-full overflow-y-auto">
      <div className="flex items-center justify-between border-b border-border pb-6">
        <div>
          <h1 className="text-3xl font-display font-bold tracking-tight flex items-center">
            <ShieldAlert className="w-8 h-8 mr-3 text-yellow-500" />
            HITL Review Queue
          </h1>
          <p className="text-muted-foreground mt-1">Pending Human-in-the-Loop operator approvals</p>
        </div>
      </div>

      {pipelinesLoading ? (
        <div className="flex justify-center p-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        </div>
      ) : pausedPipelines.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-border rounded-lg bg-card/20">
          <ShieldAlert className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-30" />
          <h3 className="text-lg font-medium">No Pending Consultations</h3>
          <p className="text-muted-foreground mt-1">All intelligence pipelines are operating nominally.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {pausedPipelines.map(pipeline => (
            <PipelineConsultations key={pipeline.id} pipeline={pipeline} />
          ))}
        </div>
      )}
    </div>
  );
}

function PipelineConsultations({ pipeline }: { pipeline: any }) {
  const { data: consultations, isLoading } = useListConsultations(pipeline.id);
  const pendingConsultations = consultations?.filter(c => c.status === 'PENDING') || [];

  if (isLoading) {
    return <Card className="p-6 animate-pulse bg-card/30"><div className="h-20" /></Card>;
  }

  if (pendingConsultations.length === 0) return null;

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-medium font-display text-muted-foreground">Pipeline: <span className="text-foreground">{pipeline.name}</span></h3>
      {pendingConsultations.map(consultation => (
        <ConsultationCard key={consultation.id} pipeline={pipeline} consultation={consultation} />
      ))}
    </div>
  );
}

function ConsultationCard({ pipeline, consultation }: { pipeline: any, consultation: Consultation }) {
  const respondMutation = useRespondToConsultation();
  const [feedback, setFeedback] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleResponse = async (decision: "approve" | "reject") => {
    setIsSubmitting(true);
    try {
      await respondMutation.mutateAsync({
        approvalId: consultation.approvalId,
        data: {
          decision,
          feedback: feedback || undefined
        }
      });
      // Optionally refetch or rely on SSE/polling on dashboard
    } catch (e) {
      console.error(e);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Card className="border-yellow-500/30 bg-card/40 backdrop-blur shadow-lg shadow-yellow-500/5">
      <CardHeader className="pb-3 border-b border-border/50">
        <div className="flex justify-between items-start">
          <div>
            <CardTitle className="text-lg text-yellow-500 flex items-center">
              Node Request: {consultation.nodeId}
            </CardTitle>
            <CardDescription className="font-mono mt-1">Function: {consultation.functionName}</CardDescription>
          </div>
          <Badge className="bg-yellow-500/20 text-yellow-500 border-yellow-500/50">PENDING APPROVAL</Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-4 space-y-4">
        <div className="bg-secondary/30 p-4 rounded-md border border-border/50 font-mono text-sm whitespace-pre-wrap">
          {consultation.message}
        </div>
        
        {consultation.arguments && Object.keys(consultation.arguments).length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Arguments Payload</h4>
            <div className="bg-background p-3 rounded border border-border font-mono text-xs overflow-x-auto">
              {JSON.stringify(consultation.arguments, null, 2)}
            </div>
          </div>
        )}

        <div className="space-y-2 mt-4 pt-4 border-t border-border/50">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Operator Feedback (Optional)</label>
          <Textarea 
            placeholder="Provide context for approval or rejection..."
            className="font-mono text-sm bg-background resize-none"
            value={feedback}
            onChange={e => setFeedback(e.target.value)}
          />
        </div>

        <div className="flex gap-3 pt-2">
          <Button 
            className="flex-1 bg-green-600 hover:bg-green-700 text-white font-mono active-elevate-2 hover-elevate"
            onClick={() => handleResponse("approve")}
            disabled={isSubmitting || respondMutation.isPending}
          >
            {isSubmitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Check className="w-4 h-4 mr-2" />}
            APPROVE
          </Button>
          <Button 
            variant="destructive"
            className="flex-1 font-mono active-elevate-2 hover-elevate"
            onClick={() => handleResponse("reject")}
            disabled={isSubmitting || respondMutation.isPending}
          >
            {isSubmitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <X className="w-4 h-4 mr-2" />}
            REJECT
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
