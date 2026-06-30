/** Map Auto-Pilot step keys → manual workflow pages (Streamlit request_main_nav parity). */

export interface ManualStepLink {
  href: string;
  label: string;
  description: string;
}

export const AUTOPILOT_STEP_KEYS = [
  "master_sync",
  "new_product_launch",
  "pull_raw_data",
  "sync_config",
  "run_engine",
  "notify",
] as const;

export const AUTOPILOT_MANUAL_LINKS: Record<string, ManualStepLink> = {
  master_sync: {
    href: "/master-data",
    label: "Master Data",
    description: "Sync & validate demand planning masters to Excel.",
  },
  new_product_launch: {
    href: "/new-product-launch?tab=sync",
    label: "Product Launch Sync",
    description: "P-H Master sync for new products and hub mappings.",
  },
  pull_raw_data: {
    href: "/baseline/load-raw",
    label: "Load Raw Data",
    description: "Pull RDS cache weeks into the active Parquet dataset.",
  },
  sync_config: {
    href: "/baseline/configure",
    label: "Configure Parameters",
    description: "Sync DP Logics worksheets and pipeline flags.",
  },
  run_engine: {
    href: "/baseline/generate",
    label: "Generate Baseline",
    description: "Run the baseline availability correction engine.",
  },
  notify: {
    href: "/settings",
    label: "Settings",
    description: "SMTP and notification recipients.",
  },
};

export const AUTOPILOT_MANUAL_STEPS = AUTOPILOT_STEP_KEYS.map((key, index) => ({
  index,
  key,
  ...AUTOPILOT_MANUAL_LINKS[key],
}));

export function manualLinkForStepKey(key: string): ManualStepLink | null {
  return AUTOPILOT_MANUAL_LINKS[key] ?? null;
}

export function manualLinkForStepIndex(index: number): ManualStepLink | null {
  const key = AUTOPILOT_STEP_KEYS[index];
  return key ? AUTOPILOT_MANUAL_LINKS[key] : null;
}
