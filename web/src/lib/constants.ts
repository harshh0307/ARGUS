export const LANGUAGES = [
  { id: "py", label: "Python", icon: "🐍" },
  { id: "js", label: "JavaScript", icon: "🟨" },
  { id: "ts", label: "TypeScript", icon: "🔷" },
  { id: "go", label: "Go", icon: "🐹" },
  { id: "ruby", label: "Ruby", icon: "💎" },
  { id: "java", label: "Java", icon: "☕" },
  { id: "php", label: "PHP", icon: "🐘" },
  { id: "cs", label: "C#", icon: "🟣" },
] as const;

export const POLL_INTERVALS = {
  health: 10_000,
  detectionRuns: 15_000,
  repositories: 30_000,
  vendors: 60_000,
  pipelineActive: 3_000,
  pipelineIdle: 30_000,
} as const;

export const PIPELINE_STEPS = [
  { key: "downloading", label: "Downloading" },
  { key: "scanning", label: "Scanning" },
  { key: "fixing", label: "Fixing" },
  { key: "pushing", label: "Pushing" },
  { key: "waiting_for_ci", label: "Waiting for CI" },
] as const;

export const SEVERITY_COLORS: Record<string, string> = {
  breaking: "text-[var(--breaking)]",
  additive: "text-[var(--passed)]",
  deprecation: "text-amber-400",
  warning: "text-slate-400",
};

export const SEVERITY_BG: Record<string, string> = {
  breaking: "bg-[var(--breaking)]/10 border-[var(--breaking)]/30 text-[var(--breaking)]",
  additive: "bg-[var(--passed)]/10 border-[var(--passed)]/30 text-[var(--passed)]",
  deprecation: "bg-amber-500/10 border-amber-500/30 text-amber-400",
  warning: "bg-slate-500/10 border-slate-500/30 text-slate-400",
};
