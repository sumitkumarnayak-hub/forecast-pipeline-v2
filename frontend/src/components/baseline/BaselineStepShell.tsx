"use client";

import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { BASELINE_STEP_META, MANUAL_BASELINE_STEPS } from "@/lib/navigation";
import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

interface Props {
  stepId: keyof typeof BASELINE_STEP_META;
  children: ReactNode;
  actions?: ReactNode;
}

export default function BaselineStepShell({ stepId, children, actions }: Props) {
  const meta = BASELINE_STEP_META[stepId];
  const total = MANUAL_BASELINE_STEPS.length;

  return (
    <AppShell
      title={meta.title}
      subtitle={meta.subtitle}
      actions={actions}
    >
      <div
        className="mb-5 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm"
        style={{ borderColor: "var(--border)", background: "var(--bg-elevated)" }}
      >
        <span className="font-semibold text-blue-600">
          Step {meta.step} of {total}
        </span>
        <span className="text-slate-400">·</span>
        <div className="flex flex-wrap items-center gap-1">
          {MANUAL_BASELINE_STEPS.map((s, i) => {
            const stepMeta = BASELINE_STEP_META[s.id];
            const done = stepMeta.step < meta.step;
            const current = s.id === stepId;
            return (
              <span key={s.id} className="inline-flex items-center gap-1">
                {i > 0 && <ChevronRight className="h-3 w-3 text-slate-300" />}
                <Link
                  href={s.href}
                  className={`rounded px-1.5 py-0.5 text-xs font-medium transition ${
                    current
                      ? "bg-blue-100 text-blue-700"
                      : done
                        ? "text-emerald-600 hover:underline"
                        : "text-slate-500 hover:text-slate-700"
                  }`}
                >
                  {stepMeta.step}
                </Link>
              </span>
            );
          })}
        </div>
      </div>

      {children}

      {meta.nextHref && meta.nextLabel && (
        <div className="mt-8 flex justify-end border-t pt-6" style={{ borderColor: "var(--border)" }}>
          <Link href={meta.nextHref} className="btn btn-primary">
            Continue to {meta.nextLabel}
            <ChevronRight className="h-4 w-4" />
          </Link>
        </div>
      )}
    </AppShell>
  );
}
