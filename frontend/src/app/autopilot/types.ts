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
