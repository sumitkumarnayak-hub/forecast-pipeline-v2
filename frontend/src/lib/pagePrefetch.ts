/**
 * Prefetch page bootstrap data on hover / idle so navigation feels instant.
 */
import api from "@/lib/api";
import { cacheGet, cacheSet } from "@/lib/queryCache";
import { writeSessionBootstrap, readSessionBootstrap, BOOTSTRAP_TTL_MS } from "@/lib/bootstrapCache";
import { prefetchNplBootstrap } from "@/lib/nplBootstrap";
import { prefetchManualSync } from "@/lib/autopilotManualSync";
import { SIDEBAR_NAV, type NavLink } from "@/lib/navigation";

const inflight = new Map<string, Promise<void>>();
let activePrefetches = 0;
const MAX_CONCURRENT = 3;

const KEYS = {
  dashboard: "dashboard:bootstrap",
  autopilotShell: "autopilot:bootstrap-shell",
  settings: "settings:bootstrap",
  validation: "validation:bootstrap",
  insights: "insights:bootstrap",
  finalPlan: "final-plan:bootstrap",
  nplContext: "npl:combined-bootstrap-v3",
  nplLogSummary: "npl:submission-log:summary:|",
} as const;

const PRIORITY_HREFS = ["/dashboard", "/autopilot", "/settings", "/new-product-launch"];

async function withConcurrencyLimit<T>(fn: () => Promise<T>): Promise<T> {
  while (activePrefetches >= MAX_CONCURRENT) {
    await new Promise(r => setTimeout(r, 120));
  }
  activePrefetches += 1;
  try {
    return await fn();
  } finally {
    activePrefetches -= 1;
  }
}

async function prefetchDashboard(): Promise<void> {
  if (cacheGet(KEYS.dashboard)) return;
  await withConcurrencyLimit(async () => {
    const { data } = await api.get("/api/dashboard/bootstrap");
    cacheSet(KEYS.dashboard, data, 300_000);
  });
}

async function prefetchAutopilot(): Promise<void> {
  prefetchManualSync();
  if (cacheGet(KEYS.autopilotShell)) return;
  await withConcurrencyLimit(async () => {
    const { data } = await api.get("/api/autopilot/bootstrap");
    cacheSet(KEYS.autopilotShell, data, 300_000);
  });
}

async function prefetchSettings(): Promise<void> {
  if (readSessionBootstrap(KEYS.settings, BOOTSTRAP_TTL_MS)) return;
  await withConcurrencyLimit(async () => {
    const { data } = await api.get("/api/settings/bootstrap");
    writeSessionBootstrap(KEYS.settings, data);
  });
}

async function prefetchValidation(): Promise<void> {
  if (readSessionBootstrap(KEYS.validation, BOOTSTRAP_TTL_MS)) return;
  await withConcurrencyLimit(async () => {
    const { data } = await api.get("/api/validation/bootstrap");
    writeSessionBootstrap(KEYS.validation, data);
  });
}

async function prefetchInsights(): Promise<void> {
  if (readSessionBootstrap(KEYS.insights, BOOTSTRAP_TTL_MS)) return;
  await withConcurrencyLimit(async () => {
    const { data } = await api.get("/api/insights/bootstrap");
    writeSessionBootstrap(KEYS.insights, data);
  });
}

async function prefetchFinalPlan(): Promise<void> {
  if (readSessionBootstrap(KEYS.finalPlan, BOOTSTRAP_TTL_MS)) return;
  await withConcurrencyLimit(async () => {
    const { data } = await api.get("/api/final-plan/bootstrap");
    writeSessionBootstrap(KEYS.finalPlan, data);
  });
}

async function prefetchNpl(): Promise<void> {
  if (readSessionBootstrap(KEYS.nplContext, 1_800_000)) return;
  await withConcurrencyLimit(() => prefetchNplBootstrap());
}

async function prefetchSubmissionLogSummary(): Promise<void> {
  if (cacheGet(KEYS.nplLogSummary)) return;
  await withConcurrencyLimit(async () => {
    const { data } = await api.get("/api/new-product-launch/submissions/log", {
      params: { view: "summary" },
    });
    cacheSet(KEYS.nplLogSummary, data, 300_000);
  });
}

async function prefetchMasterDataLight(): Promise<void> {
  const jobs: Promise<void>[] = [];
  if (!cacheGet("master:sync-history")) {
    jobs.push(
      withConcurrencyLimit(() =>
        api.get("/api/master-data/sync-history").then(({ data }) => {
          cacheSet("master:sync-history", data, 300_000);
        }),
      ),
    );
  }
  if (!cacheGet("master:snapshot-runs")) {
    jobs.push(
      withConcurrencyLimit(() =>
        api.get("/api/master-data/snapshot-runs").then(({ data }) => {
          cacheSet("master:snapshot-runs", data || [], 300_000);
        }),
      ),
    );
  }
  await Promise.allSettled(jobs);
}

function matchPrefetch(href: string): (() => Promise<void>) | null {
  if (href.startsWith("/settings")) return prefetchSettings;
  if (href.startsWith("/new-product-launch")) {
    return async () => {
      await prefetchNpl();
      await prefetchSubmissionLogSummary();
    };
  }
  return null;
}

export function prefetchRoute(href: string): void {
  const fn = matchPrefetch(href);
  if (!fn) return;
  const key = `route:${href}`;
  if (inflight.has(key)) return;
  const job = fn()
    .catch(() => {})
    .finally(() => inflight.delete(key));
  inflight.set(key, job);
}

function collectNavLinks(role: string): NavLink[] {
  const links: NavLink[] = [];
  for (const entry of SIDEBAR_NAV) {
    if (entry.type === "link") {
      if (entry.roles.includes(role)) links.push(entry);
    } else if (entry.roles.includes(role)) {
      links.push(...entry.children.filter(c => c.roles.includes(role)));
    }
  }
  return links;
}

/** Warm all role-visible routes after login (priority first, then secondary). */
export function prefetchAllRoutes(role: string): void {
  const links = collectNavLinks(role);
  const priority = links.filter(l =>
    PRIORITY_HREFS.some(p => l.href === p || l.href.startsWith(`${p}/`)),
  );
  const secondary = links.filter(l => !priority.includes(l));

  const schedule = (items: NavLink[], startMs: number) => {
    items.forEach((link, i) => {
      window.setTimeout(() => prefetchRoute(link.href), startMs + i * 700);
    });
  };

  const run = () => {
    prefetchNpl();
    schedule(priority, 300);
    schedule(secondary, 2200);
  };

  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(() => run(), { timeout: 2500 });
  } else {
    window.setTimeout(run, 400);
  }
}

export const prefetchPriorityRoutes = prefetchAllRoutes;
