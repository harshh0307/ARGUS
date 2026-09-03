"use client";

import { usePipelineRuns } from "@/hooks/use-pipeline-runs";
import { PIPELINE_STEPS } from "@/lib/constants";
import { formatRelativeTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { ExternalLink, Check, AlertCircle, Clock, Loader2 } from "lucide-react";

function StepIndicator({ currentStep }: { currentStep: string | null }) {
  if (!currentStep) return null;
  const currentIdx = PIPELINE_STEPS.findIndex((s) => s.key === currentStep);

  return (
    <div className="flex items-center gap-1 mt-2">
      {PIPELINE_STEPS.map((step, i) => (
        <div key={step.key} className="flex items-center gap-1">
          <div
            className={`w-2 h-2 rounded-full ${
              i < currentIdx
                ? "bg-[var(--passed)]"
                : i === currentIdx
                  ? "bg-[var(--agent)] animate-pulse"
                  : "bg-[var(--muted-foreground)]/30"
            }`}
          />
          {i < PIPELINE_STEPS.length - 1 && (
            <div
              className={`w-4 h-0.5 ${
                i < currentIdx ? "bg-[var(--passed)]" : "bg-[var(--muted-foreground)]/20"
              }`}
            />
          )}
        </div>
      ))}
      <span className="text-[10px] text-[var(--muted-foreground)] ml-1">
        {PIPELINE_STEPS.find((s) => s.key === currentStep)?.label ?? currentStep}
      </span>
    </div>
  );
}

function PipelineRunCard({ run }: { run: { id: number; status: string; current_step: string | null; pr_number: number | null; pr_url: string | null; error_message: string | null; created_at: string; repository_id: number } }) {
  const statusConfig: Record<string, { color: string; icon: typeof Check; label: string }> = {
    success: { color: "text-[var(--passed)]", icon: Check, label: "Complete" },
    failed: { color: "text-[var(--breaking)]", icon: AlertCircle, label: "Failed" },
    running: { color: "text-[var(--agent)]", icon: Loader2, label: "Running" },
    queued: { color: "text-[var(--muted-foreground)]", icon: Clock, label: "Queued" },
  };
  const cfg = statusConfig[run.status] ?? statusConfig.queued;
  const Icon = cfg.icon;

  return (
    <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] space-y-1">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className={`h-3.5 w-3.5 ${cfg.color} ${run.status === "running" ? "animate-spin" : ""}`} />
          <span className="text-xs font-medium">Pipeline #{run.id}</span>
        </div>
        <Badge
          variant="outline"
          className={`text-[10px] px-1.5 py-0 ${
            run.status === "success"
              ? "border-[var(--passed)]/30 text-[var(--passed)]"
              : run.status === "failed"
                ? "border-[var(--breaking)]/30 text-[var(--breaking)]"
                : run.status === "running"
                  ? "border-[var(--agent)]/30 text-[var(--agent)]"
                  : ""
          }`}
        >
          {cfg.label}
        </Badge>
      </div>
      {run.status === "running" && <StepIndicator currentStep={run.current_step} />}
      {run.pr_number && run.pr_url && (
        <a
          href={run.pr_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-[var(--agent)] hover:underline"
        >
          PR #{run.pr_number} <ExternalLink className="h-3 w-3" />
        </a>
      )}
      {run.error_message && (
        <p className="text-[10px] text-[var(--breaking)] line-clamp-2">{run.error_message}</p>
      )}
      <p className="text-[10px] text-[var(--muted-foreground)]">{formatRelativeTime(run.created_at)}</p>
    </div>
  );
}

export function PipelinePanel() {
  const { runs, activeRun, isLoading } = usePipelineRuns(10);

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-[var(--foreground)]">Pipeline Runs</h3>
        {activeRun && (
          <Badge variant="outline" className="text-[10px] border-[var(--agent)]/30 text-[var(--agent)]">
            <Loader2 className="h-2.5 w-2.5 mr-1 animate-spin" /> Active
          </Badge>
        )}
      </div>
      <ScrollArea className="h-[300px]">
        <div className="space-y-2 pr-2">
          {runs.length === 0 ? (
            <p className="text-xs text-[var(--muted-foreground)] text-center py-8">
              No pipeline runs yet
            </p>
          ) : (
            runs.map((run) => <PipelineRunCard key={run.id} run={run} />)
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
