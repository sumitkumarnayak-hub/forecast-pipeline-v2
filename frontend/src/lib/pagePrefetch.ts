/**
 * Prefetch page bootstrap data on hover / idle so navigation feels instant.
 * Uses the same cache keys as each page's stale-while-revalidate loader.
 */
import api from "@/lib/api";
import { cacheGet, cacheSet } from "@/lib/queryCache";
import { writeSessionBootstrap, readSessionBootstrap, BOOTSTRAP_TTL_MS } from "@/lib/bootstrapCache";
import { SIDEBAR_NAV, type NavLink } from "@/lib/navigation";

const inflight = new Map<string, Promise<void>>();

const KEYS = {
  dashboard: "dashboard:bootstrap",
  autopilotShell: "autopilot:bootstrap-shell",
  autopilotState: "autopilot:run-state",
  settings: "settings:bootstrap",
  validation: "validation:bootstrap",
  insights: "insights:bootstrap",
  finalPlan: "final-plan:bootstrap",
  nplContext: "npl:wizard-context",
} as const;

async function prefetchDashboard(): Promise<void> {
  if (cacheGet(KEYS.dashboard)) return;
  const { data } = await api.get("/api/dashboard/bootstrap");
  cacheSet(KEYS.dashboard, data, 180_000);
}

async function prefetchAutopilot(): Promise<void> {
  if (!cacheGet(KEYS.autopilotShell)) {
    const { data } = await api.get("/api/autopilot/bootstrap");
    cacheSet(KEYS.autopilotShell, data, 120_000);
  }
  if (!cacheGet(KEYS.autopilotState)) {
    try {
      const { data } = await api.get("/api/autopilot/state");
      cacheSet(KEYS.autopilotState, data, 15_000);
    } catch {
      /* state may timeout — shell still helps */
    }
  }
}

async function prefetchSettings(): Promise<void> {
  if (readSessionBootstrap(KEYS.settings, BOOTSTRAP_TTL_MS)) return;
  const { data } = await api.get("/api/settings/bootstrap");
  writeSessionBootstrap(KEYS.settings, data);
}

async function prefetchValidation(): Promise<void> {
  if (readSessionBootstrap(KEYS.validation, BOOTSTRAP_TTL_MS)) return;
  const { data } = await api.get("/api/validation/bootstrap");
  writeSessionBootstrap(KEYS.validation, data);
}

async function prefetchInsights(): Promise<void> {
  if (readSessionBootstrap(KEYS.insights, BOOTSTRAP_TTL_MS)) return;
  const { data } = await api.get("/api/insights/bootstrap");
  writeSessionBootstrap(KEYS.insights, data);
}

async function prefetchFinalPlan(): Promise<void> {
  if (readSessionBootstrap(KEYS.finalPlan, BOOTSTRAP_TTL_MS)) return;
  const { data } = await api.get("/api/final-plan/bootstrap");
  writeSessionBootstrap(KEYS.finalPlan, data);
}

async function prefetchNpl(): Promise<void> {
  if (readSessionBootstrap(KEYS.nplContext, BOOTSTRAP_TTL_MS)) return;
  try {
    const { data } = await api.get("/api/new-product-launch/wizard/context");
    writeSessionBootstrap(KEYS.nplContext, data);
  } catch {
    /* optional */
  }
}

async function prefetchMasterDataLight(): Promise<void> {
  const jobs: Promise<void>[] = [];
  if (!cacheGet("master:sync-history")) {
    jobs.push(
      api.get("/api/master-data/sync-history").then(({ data }) => {
        cacheSet("master:sync-history", data, 120_000);
      }),
    );
  }
  if (!cacheGet("master:snapshot-runs")) {
    jobs.push(
      api.get("/api/master-data/snapshot-runs").then(({ data }) => {
        cacheSet("master:snapshot-runs", data || [], 120_000);
      }),
    );
  }
  if (!cacheGet("master:legacy-sync-types")) {
    jobs.push(
      api.get("/api/master-data/legacy-sync-types").then(({ data }) => {
        cacheSet("master:legacy-sync-types", data || [], 120_000);
      }),
    );
  }
  await Promise.allSettled(jobs);
}

function matchPrefetch(href: string): (() => Promise<void>) | null {
  if (href.startsWith("/dashboard")) return prefetchDashboard;
  if (href.startsWith("/autopilot")) return prefetchAutopilot;
  if (href.startsWith("/settings")) return prefetchSettings;
  if (href.startsWith("/validation")) return prefetchValidation;
  if (href.startsWith("/analytics")) return prefetchInsights;
  if (href.startsWith("/final-plan")) return prefetchFinalPlan;
  if (href.startsWith("/new-product-launch")) return prefetchNpl;
  if (href.startsWith("/master-data")) return prefetchMasterDataLight;
  return null;
}

/** Prefetch bootstrap for a sidebar route (deduped). */
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

/** Warm all allowed routes after login (idle, staggered). */
export function prefetchAllRoutes(role: string): void {
  const links = collectNavLinks(role);
  const run = () => {
    links.forEach((link, i) => {
      window.setTimeout(() => prefetchRoute(link.href), i * 250);
    });
  };
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(() => run(), { timeout: 3000 });
  } else {
    window.setTimeout(run, 800);
  }
}
