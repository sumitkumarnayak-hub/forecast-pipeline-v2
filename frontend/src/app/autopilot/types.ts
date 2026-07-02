export type UiStatus = "idle" | "running" | "failed" | "success";

export interface StepConfig {
  name: string;
  desc: string;
  icon: string;
}

export interface StepRow {
  index: number;
  key: string;
  name: string;
  icon: string;
  status: string;
  detail: string;
  source?: "autopilot" | "manual";
}

export interface ManualSyncStep {
  index: number;
  key: string;
  name: string;
  detected: boolean;
  confidence: string;
  message: string;
  evidence: string;
}

export interface ManualSyncResult {
  completed_steps: number[];
  suggested_from_step: number;
  steps: ManualSyncStep[];
  summary: string;
  checked_at: string;
}

export interface Bootstrap {
  read_only: boolean;
  steps_config: StepConfig[];
  state: Record<string, unknown> | null;
  ui_status: UiStatus;
  resume_step: number | null;
  step_idx: number;
  progress_pct: number;
  step_rows: StepRow[];
  run_log: string;
  output_paths: Record<string, string>;
  output_paths_reference?: { step: string; label: string; path: string }[];
  state_pending?: boolean;
  state_error?: string;
}
