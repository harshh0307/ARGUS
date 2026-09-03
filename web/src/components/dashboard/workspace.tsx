"use client";

import { useDetectionRuns } from "@/hooks/use-detection-runs";
import { WorkspaceLeft } from "./workspace-left";
import { WorkspaceMiddle } from "./workspace-middle";
import { WorkspaceRight } from "./workspace-right";

export function Workspace() {
  const { selectedRun } = useDetectionRuns();

  return (
    <div
      className="grid grid-cols-12 gap-4"
      style={{ height: "calc(100vh - 280px)" }}
    >
      <div className="col-span-12 lg:col-span-3">
        <WorkspaceLeft />
      </div>
      <div className="col-span-12 lg:col-span-5">
        <WorkspaceMiddle />
      </div>
      <div className="col-span-12 lg:col-span-4">
        <WorkspaceRight key={selectedRun?.id ?? "none"} />
      </div>
    </div>
  );
}
