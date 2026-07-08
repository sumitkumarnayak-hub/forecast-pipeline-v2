"use client";

import AppShell from "@/components/layout/AppShell";
import HubLaunchTab from "@/components/npl/HubLaunchTab";

export default function HubLaunchPage() {
  return (
    <AppShell
      title="Hub Launch"
      subtitle="Configure new hub mappings by cloning rows from reference source hubs"
    >
      <div className="card" style={{ padding: "1.5rem" }}>
        <HubLaunchTab />
      </div>
    </AppShell>
  );
}
