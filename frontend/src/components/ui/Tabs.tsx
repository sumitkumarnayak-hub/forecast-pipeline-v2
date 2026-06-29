import React, { useState } from "react";

interface Tab {
  id: string;
  label: React.ReactNode;
  content: React.ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  defaultTab?: string;
}

export function Tabs({ tabs, defaultTab }: TabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab || tabs[0].id);

  return (
    <div style={{ width: "100%" }}>
      <div 
        className="tabs-scroll"
        style={{
          display: "flex",
          borderBottom: "1px solid var(--border)",
          gap: "0.5rem",
          marginBottom: "1.5rem",
          overflowX: "auto",
          whiteSpace: "nowrap",
          scrollbarWidth: "none", // Hide scrollbar Firefox
          WebkitOverflowScrolling: "touch",
        }}
      >
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: "0.65rem 1.15rem",
                fontSize: "0.85rem",
                fontWeight: 600,
                background: "none",
                border: "none",
                cursor: "pointer",
                transition: "color 0.15s, border-color 0.15s",
                color: isActive ? "var(--blue)" : "var(--text-muted)",
                borderBottom: isActive ? "2px solid var(--blue)" : "2px solid transparent",
                marginBottom: "-1px",
                outline: "none",
                whiteSpace: "nowrap", // Ensure tab text never wraps
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div>
        {tabs.find((t) => t.id === activeTab)?.content}
      </div>
    </div>
  );
}
