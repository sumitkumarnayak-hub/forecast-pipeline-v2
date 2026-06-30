/** Client-side Auto-Pilot defaults — instant render before API responds. */
import type { Bootstrap, StepRow } from "@/app/autopilot/types";

const STEPS_CONFIG = [
  {
    name: "Step 1: Master Data Sync & Validation",
    desc: "Read Google Sheets masters, run Polars validation, export to Product_Masters.xlsx.",
    icon: "clipboard",
  },
  {
    name: "Step 2: New Product Launch (P-H Master)",
    desc: "Auto-discover new products in P Master and append P-H Master rows for all active hubs.",
    icon: "rocket",
  },
  {
    name: "Step 3: Pull Raw Data",
    desc: "Fetch the latest week of raw actuals from RDS cache and update the active Parquet dataset.",
    icon: "download",
  },
  {
    name: "Step 4: Sync Config Parameters",
    desc: "Sync DP Logics worksheets (City_Cat, STF, Percentile, Avl_Flag, etc.) to local Excel.",
    icon: "settings",
  },
  {
    name: "Step 5: Run Baseline Engine",
    desc: "Execute optimized_baseline_avail_correction.py on the active dataset.",
    icon: "calculator",
  },
  {
    name: "Step 6: Email Notification",
    desc: "Send success notification when all prior steps complete.",
    icon: "mail",
  },
] as const;

const STEP_KEYS = [
  "master_sync",
  "new_product_launch",
  "pull_raw_data",
  "sync_config",
  "run_engine",
  "notify",
];

function defaultStepRows(): StepRow[] {
  return STEPS_CONFIG.map((cfg, index) => ({
    index,
    key: STEP_KEYS[index] || "",
    name: cfg.name,
    icon: cfg.icon,
    status: "ready",
    detail: "",
  }));
}

export function createDefaultBootstrap(readOnly = false): Bootstrap {
  return {
    read_only: readOnly,
    steps_config: [...STEPS_CONFIG],
    state: null,
    ui_status: "idle",
    resume_step: null,
    step_idx: 0,
    progress_pct: 0,
    step_rows: defaultStepRows(),
    run_log: "",
    output_paths: {},
    output_paths_reference: [],
  };
}
