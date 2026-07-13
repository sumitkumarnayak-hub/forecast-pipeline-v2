/**
 * Sidebar & page hierarchy — mirrors Streamlit NAV_PAGES + nested tabs.
 * Source: forecast-pipeline-new-codebase (sidebar.py, router.py, optimized_baseline.py)
 */
import type { ElementType } from "react";
import {
  LayoutDashboard,
  Zap,
  Download,
  SlidersHorizontal,
  PlayCircle,
  SearchCheck,
  BadgeCheck,
  Database,
  Package,
  // LineChart,
  Settings,
  ClipboardList,
  // ShieldCheck,
  BookOpen,
} from "lucide-react";

export interface NavLink {
  type: "link";
  id: string;
  label: string;
  href: string;
  icon: ElementType;
  roles: string[];
  lockUntilBaselineApproved?: boolean;
}

export interface NavGroup {
  type: "group";
  id: string;
  label: string;
  caption?: string;
  roles: string[];
  children: NavLink[];
}

export type NavEntry = NavLink | NavGroup;

export const MANUAL_BASELINE_STEPS: NavLink[] = [
  {
    type: "link",
    id: "load-raw",
    label: "1. Load Raw Data",
    href: "/baseline/load-raw",
    icon: Download,
    roles: ["admin", "planner"],
  },
  {
    type: "link",
    id: "configure",
    label: "2. Configure Parameters",
    href: "/baseline/configure",
    icon: SlidersHorizontal,
    roles: ["admin", "planner"],
  },
  {
    type: "link",
    id: "generate",
    label: "3. Generate Baseline",
    href: "/baseline/generate",
    icon: PlayCircle,
    roles: ["admin", "planner"],
  },
  {
    type: "link",
    id: "review",
    label: "4. Review & Validate",
    href: "/baseline/review",
    icon: SearchCheck,
    roles: ["admin", "planner"],
  },
  {
    type: "link",
    id: "approve",
    label: "5. Approve Baseline",
    href: "/baseline/approve",
    icon: BadgeCheck,
    roles: ["admin", "planner"],
  },
];

/** Streamlit NAV_PAGES order */
export const SIDEBAR_NAV: NavEntry[] = [
  {
    type: "link",
    id: "dashboard",
    label: "Dashboard",
    href: "/dashboard",
    icon: LayoutDashboard,
    roles: ["admin", "planner", "viewer"],
  },
  {
    type: "link",
    id: "autopilot",
    label: "Auto-Pilot",
    href: "/autopilot",
    icon: Zap,
    roles: ["admin", "planner"],
  },
  {
    type: "group",
    id: "manual-baseline",
    label: "Manual Baseline",
    caption: "Follow steps 1 → 5",
    roles: ["admin", "planner"],
    children: MANUAL_BASELINE_STEPS,
  },
  {
    type: "link",
    id: "master-data",
    label: "Master Data",
    href: "/master-data",
    icon: Database,
    roles: ["admin", "planner", "viewer"],
  },
  {
    type: "link",
    id: "product-launch",
    label: "Product Launch",
    href: "/new-product-launch",
    icon: Package,
    roles: ["admin", "planner", "product"],
  },
  {
    type: "link",
    id: "hub-launch",
    label: "Hub Launch",
    href: "/hub-launch",
    icon: Zap,
    roles: ["admin", "planner","product"],
  },
  {
    type: "link",
    id: "final-plan",
    label: "Final Plan",
    href: "/final-plan",  
    icon: ClipboardList,
    roles: ["admin", "planner"],
    lockUntilBaselineApproved: true,
  },
  // {
  //   type: "link",
  //   id: "validation",
  //   label: "Validation",
  //   href: "/validation",
  //   icon: ShieldCheck,
  //   roles: ["admin", "planner"],
  // },
  // {
  //   type: "link",
  //   id: "analytics",
  //   label: "Analytics",
  //   href: "/analytics",
  //   icon: LineChart,
  //   roles: ["admin", "planner", "viewer"],
  // },
  {
    type: "link",
    id: "settings",
    label: "Settings",
    href: "/settings",
    icon: Settings,
    roles: ["admin", "planner", "viewer", "product"],
  },
  {
    type: "link",
    id: "about",
    label: "About & Guide",
    href: "/about",
    icon: BookOpen,
    roles: ["admin", "planner", "viewer"],
  },
];

export const BASELINE_STEP_META: Record<
  string,
  { step: number; title: string; subtitle: string; nextHref: string | null; nextLabel: string | null }
> = {
  "load-raw": {
    step: 1,
    title: "Load Raw Data",
    subtitle: "Fetch weekly actuals from RDS and build the active dataset",
    nextHref: "/baseline/configure",
    nextLabel: "2. Configure Parameters",
  },
  configure: {
    step: 2,
    title: "Configure Parameters",
    subtitle: "Pipeline toggles and DP Logics worksheet sync",
    nextHref: "/baseline/generate",
    nextLabel: "3. Generate Baseline",
  },
  generate: {
    step: 3,
    title: "Generate Baseline",
    subtitle: "Run the baseline engine and write Summary output",
    nextHref: "/baseline/review",
    nextLabel: "4. Review & Validate",
  },
  review: {
    step: 4,
    title: "Review & Validate",
    subtitle: "Inspect summary output and base-plan comparison",
    nextHref: "/baseline/approve",
    nextLabel: "5. Approve Baseline",
  },
  approve: {
    step: 5,
    title: "Approve Baseline",
    subtitle: "Lock the baseline and unlock Final Plan (admin approval)",
    nextHref: null,
    nextLabel: null,
  },
};

/** Nested tab trees per page (Streamlit parity) */
export const PAGE_TAB_TREES = {
  masterData: {
    top: [
      { id: "demand", label: "Demand Planning Masters" },
      { id: "inventory", label: "Inventory Buffer Master" },
      { id: "history", label: "Master Sync History" },
    ],
    demand: [
      { id: "p-master", label: "P Master" },
      { id: "ph-master", label: "P-H Master" },
      { id: "hub-master", label: "Hub Master" },
    ],
  },
  analytics: {
    top: [
      { id: "insights", label: "Insights" },
      { id: "reports", label: "Reports" },
    ],
  },
  productLaunch: {
    top: [
      { id: "launch", label: "Launch Planning" },
      { id: "sync-ph", label: "Sync to P-H Master" },
      { id: "auto-sync", label: "Auto Sync" },
    ],
    launch: [
      { id: "type1", label: "New Product Launch" },
      { id: "type2", label: "Product Expansion" },
      { id: "type3", label: "Product Replacement" },
      { id: "history", label: "Submission History" },
    ],
  },
  configureParams: {
    top: [{ id: "masters", label: "Configuration Masters" }],
  },
  reviewBaseline: {
    top: [
      { id: "city-day", label: "City × Day" },
      { id: "city-cat-day", label: "City × Category × Day" },
      { id: "hub-cat-day", label: "Hub × Category × Day" },
      { id: "hub-day", label: "Hub × Day" },
    ],
  },
} as const;

/** Resolve allowed roles for a pathname (longest prefix match). */
export function rolesForPath(pathname: string): string[] | null {
  const flat: NavLink[] = [];
  for (const entry of SIDEBAR_NAV) {
    if (entry.type === "link") flat.push(entry);
    else flat.push(...entry.children);
  }
  flat.sort((a, b) => b.href.length - a.href.length);
  for (const link of flat) {
    if (pathname === link.href || pathname.startsWith(`${link.href}/`)) {
      return link.roles;
    }
  }
  if (pathname.startsWith("/baseline")) {
    return ["admin", "planner"];
  }
  return null;
}

/** Default landing route after login (first page the role can access). */
export function homePathForRole(role: string): string {
  if (role === "product") return "/new-product-launch";
  return "/dashboard";
}
