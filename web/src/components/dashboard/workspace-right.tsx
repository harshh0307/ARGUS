"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sparkles,
  Code,
  ShieldCheck,
  GitBranch,
  Check,
  Clock,
  AlertCircle,
} from "lucide-react";

const PIPELINE_STEPS = [
  {
    name: "Ingest Spec",
    description: "Fetch & diff OpenAPI specification",
    icon: Sparkles,
    status: "complete" as const,
  },
  {
    name: "AST Impact",
    description: "Scan codebase for affected call sites",
    icon: Code,
    status: "complete" as const,
  },
  {
    name: "LangGraph Fix",
    description: "LLM generates patch suggestions",
    icon: Sparkles,
    status: "complete" as const,
  },
  {
    name: "Guardrail Audit",
    description: "Validate syntax, semantics, prompts",
    icon: ShieldCheck,
    status: "complete" as const,
  },
  {
    name: "PR & CI Loop",
    description: "Open PR, wait for CI, retry on failure",
    icon: GitBranch,
    status: "complete" as const,
  },
];

const GUARDRAILS = [
  { name: "Syntax Validation", detail: "ast.parse / JS bracket check", status: "pass" },
  { name: "Unreachable Code", detail: "Dead code after raise/return", status: "pass" },
  { name: "Throw-in-Expression", detail: "JS throw in IIFE/expression", status: "pass" },
  { name: "Semantic Guard", detail: "Re-scan patched AST for removed calls", status: "pass" },
  { name: "Duplicate Patch", detail: "Same patch signature detected", status: "pass" },
  { name: "Progress Stall", detail: "Same error twice in a row", status: "pass" },
  { name: "Rate Limit", detail: "Exponential backoff on 429", status: "pass" },
  { name: "Token Budget", detail: "Context window fit check", status: "pass" },
  { name: "Cost Tracker", detail: "Per-model pricing enforced", status: "pass" },
  { name: "Prompt Sanitizer", detail: "13 injection patterns stripped", status: "pass" },
];

export function WorkspaceRight() {
  return (
    <div className="flex flex-col h-full bg-[var(--card)] border border-[var(--border)] rounded-lg overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-[var(--border)]">
        <h2 className="text-sm font-semibold">
          LangGraph Agent Execution &amp; Guardrails
        </h2>
      </div>

      <ScrollArea className="flex-1 p-4 space-y-6">
        {/* Step Trace */}
        <div className="space-y-1">
          <h3 className="text-[10px] font-medium text-[var(--muted-foreground)] uppercase tracking-wider mb-3">
            Pipeline Steps
          </h3>
          <div className="relative">
            {/* Vertical line */}
            <div className="absolute left-[11px] top-4 bottom-4 w-px bg-[var(--agent)]/30" />
            {PIPELINE_STEPS.map((step, i) => (
              <div key={i} className="flex items-start gap-3 relative py-2">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 z-10 ${
                    step.status === "complete"
                      ? "bg-[var(--agent)]/20 border border-[var(--agent)]/50"
                      : step.status === "running"
                      ? "bg-[var(--agent)]/30 border border-[var(--agent)] animate-pulse"
                      : "bg-[var(--surface)] border border-[var(--border)]"
                  }`}
                >
                  {step.status === "complete" ? (
                    <Check className="h-3 w-3 text-[var(--agent)]" />
                  ) : step.status === "running" ? (
                    <Clock className="h-3 w-3 text-[var(--agent)]" />
                  ) : (
                    <AlertCircle className="h-3 w-3 text-[var(--muted-foreground)]" />
                  )}
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-medium">{step.name}</div>
                  <div className="text-[10px] text-[var(--muted-foreground)]">
                    {step.description}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Guardrails Checklist */}
        <div className="space-y-1">
          <h3 className="text-[10px] font-medium text-[var(--muted-foreground)] uppercase tracking-wider mb-3">
            Guardrails Checklist
          </h3>
          <div className="space-y-1">
            {GUARDRAILS.map((g, i) => (
              <div
                key={i}
                className="flex items-center gap-2 text-[10px] py-1 px-2 rounded hover:bg-[var(--surface-hover)]"
              >
                <ShieldCheck
                  className={`h-3 w-3 shrink-0 ${
                    g.status === "pass"
                      ? "text-[var(--passed)]"
                      : "text-[var(--muted-foreground)]"
                  }`}
                />
                <span className="font-medium">{g.name}</span>
                <span className="text-[var(--muted-foreground)] ml-auto">
                  {g.detail}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Terminal Log */}
        <div className="space-y-1">
          <h3 className="text-[10px] font-medium text-[var(--muted-foreground)] uppercase tracking-wider mb-3">
            Agent Execution Log
          </h3>
          <div className="bg-black/50 rounded-lg p-3 font-mono text-[10px] max-h-40 overflow-y-auto border border-[var(--border)]">
            <div className="text-[var(--passed)]">$ argus pipeline --auto</div>
            <div className="text-[var(--muted-foreground)] mt-1">
              [ingest] Fetching spec for github...
            </div>
            <div className="text-[var(--muted-foreground)]">
              [detect] 3 breaking changes found
            </div>
            <div className="text-[var(--muted-foreground)]">
              [scan] Scanning 4 repositories...
            </div>
            <div className="text-[var(--passed)]">
              [fix] 2/3 patches applied successfully
            </div>
            <div className="text-[var(--semantic)]">
              [pr] PR #142 opened, CI running...
            </div>
            <div className="text-[var(--passed)]">
              [ci] All checks passed after 1 attempt
            </div>
            <div className="text-[var(--passed)]">
              [merge] PR #142 squash-merged
            </div>
            <div className="text-[var(--muted-foreground)] mt-1">
              Agent execution logs will appear here when a pipeline runs.
            </div>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
