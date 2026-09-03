"use client";

import { useState } from "react";
import { Header } from "@/components/layout/header";
import { BottomDrawer } from "@/components/layout/bottom-drawer";
import { AnalyticsGrid } from "@/components/dashboard/analytics-grid";
import { Workspace } from "@/components/dashboard/workspace";
import { VendorsPage } from "@/components/vendors/vendors-page";
import { FadeIn } from "@/components/ui/motion";

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<"dashboard" | "vendors">("dashboard");

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        {activeTab === "dashboard" ? (
          <>
            <FadeIn delay={0}>
              <AnalyticsGrid />
            </FadeIn>
            <FadeIn delay={0.1}>
              <Workspace />
            </FadeIn>
          </>
        ) : (
          <FadeIn delay={0}>
            <VendorsPage />
          </FadeIn>
        )}
      </main>
      {activeTab === "dashboard" && <BottomDrawer />}
    </div>
  );
}
