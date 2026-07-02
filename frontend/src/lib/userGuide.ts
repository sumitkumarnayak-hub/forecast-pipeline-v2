/**
 * In-app user guide for Planning Suite — plain language for new team members.
 */

export type GuideSection = {
  id: string;
  title: string;
  icon?: string;
  paragraphs?: string[];
  bullets?: string[];
  steps?: { title: string; body: string }[];
  table?: { headers: string[]; rows: string[][] };
  tip?: string;
};

export const GUIDE_INTRO = {
  title: "Planning Suite — Team Guide",
  subtitle:
    "A simple walkthrough of the demand planning tool: what each page does, how the weekly workflow fits together, and what your role can do.",
  version: "2.0",
};

export const GUIDE_SECTIONS: GuideSection[] = [
  {
    id: "what-is-this",
    title: "What is Planning Suite?",
    paragraphs: [
      "Planning Suite helps the demand planning team run the weekly forecast cycle: sync master data, pull latest sales actuals, generate a baseline forecast, approve it, and produce the final plan.",
      "It also supports new product launches (city/hub level) and tracks submission history in Google Sheets.",
      "Most numbers live in Google Sheets and shared drive folders. The app reads and writes those sources — it is the control panel, not the only database.",
    ],
  },
  {
    id: "roles",
    title: "Roles — what you can do",
    table: {
      headers: ["Role", "Typical user", "Can do"],
      rows: [
        [
          "Admin",
          "Team lead / IT",
          "Everything: approve baseline, manage users & email alerts, run Auto-Pilot, edit masters",
        ],
        [
          "Planner",
          "Demand planner",
          "Run pipelines, edit masters, product launches, baseline steps — cannot approve baseline or manage users",
        ],
        [
          "Viewer",
          "Stakeholder",
          "Read-only: Dashboard, Master Data views, Analytics, Settings profile",
        ],
      ],
    },
    tip: "If a button is missing or a page says “access denied”, ask an admin to check your role under Settings → Users.",
  },
  {
    id: "weekly-flow",
    title: "Recommended weekly workflow",
    steps: [
      {
        title: "1. Check the Dashboard",
        body: "Pick the latest week, review KPIs and deltas. Confirm data looks reasonable before running anything heavy.",
      },
      {
        title: "2. Run Auto-Pilot (fastest path)",
        body: "Go to Auto-Pilot → Run from step 1. This syncs masters, updates P-H for new products, pulls raw data, syncs config, runs the baseline engine, and sends email when done. Watch the progress log for errors.",
      },
      {
        title: "2b. Or use Manual Baseline (step-by-step)",
        body: "Use Manual Baseline steps 1→5 if you need to pause between steps, re-run one step only, or debug a failure. Same end result as Auto-Pilot, but you control each step.",
      },
      {
        title: "3. Review & approve baseline",
        body: "Open Manual Baseline → Review & Validate, then Approve Baseline. Only an admin can approve. Until approved, Final Plan stays locked.",
      },
      {
        title: "4. Run Final Plan",
        body: "After approval, open Final Plan: sync adhoc/inventory inputs if needed, then run the final plan engine.",
      },
      {
        title: "5. Product Launch (as needed)",
        body: "Not every week — use Product Launch when adding/expanding/replacing products. Check Submission History for status and admin approval.",
      },
      {
        title: "6. Validation & Analytics",
        body: "Use Validation to check baseline output files. Use Analytics for deeper insights and reports.",
      },
    ],
  },
  {
    id: "pages",
    title: "Page-by-page guide",
    bullets: [
      "Dashboard — Week selector, KPI cards, plan vs baseline tables, inventory buffer, new hubs/products.",
      "Auto-Pilot — One-click (or resume-from-step) pipeline. Check History tab for past runs.",
      "Manual Baseline — Five steps: Load Raw Data → Configure → Generate → Review → Approve.",
      "Master Data — View/sync P Master, P-H Master, Hub Mapping, inventory buffer. Hub Changes for remapping.",
      "Product Launch — Wizard for new launch, expansion, replacement; Submission History for tracking.",
      "Final Plan — Unlocked after baseline approval. Sync inputs and run final plan.",
      "Validation — Upload or validate baseline summary Excel; view validation logs.",
      "Analytics — Insights charts and Reports (availability loss, 6-week summaries).",
      "Settings — Your profile & preferences. Admins: Users, email recipients, test email, session info.",
      "About (this page) — Team guide and app overview.",
    ],
  },
  {
    id: "autopilot-vs-manual",
    title: "Auto-Pilot vs Manual Baseline",
    paragraphs: [
      "Auto-Pilot runs all six steps in sequence with live progress. Use it for the normal weekly run when masters and drive paths are healthy.",
      "Manual Baseline is for operators who need visibility into each step — for example, re-pulling raw data without re-running the engine, or fixing config before generate.",
      "Both paths write to the same files and sheets. Do not run Auto-Pilot and manual generate at the same time.",
      "On Auto-Pilot, click Sync manual progress to detect steps you already finished manually and start from the next step.",
    ],
  },
  {
    id: "product-launch",
    title: "Product Launch in brief",
    steps: [
      {
        title: "Pick launch type",
        body: "New Product Launch, Expansion (more cities/hubs), or Replacement (swap an old SKU).",
      },
      {
        title: "Download template & upload",
        body: "Fill the Excel template with city or hub level volumes, upload, and fix any validation errors shown.",
      },
      {
        title: "Set launch date & submit",
        body: "Choose a valid Monday (T+4 rule). Submit sends rows to the Submission_Log sheet.",
      },
      {
        title: "Track in Submission History",
        body: "Click a submission to see hub-level detail. Admins approve or reject from there.",
      },
    ],
  },
  {
    id: "tips",
    title: "Tips & common issues",
    bullets: [
      "First load of Product Launch or Master Data can be slow — Google Sheets is being read. A second visit is much faster (cached).",
      "If Auto-Pilot shows “running” forever after a server restart, check with admin — the backend may need a fresh run.",
      "“Cannot reach API” on login — backend is down or wrong URL. In dev, start backend on port 8000.",
      "Session expired — log in again. Cookies require HTTPS in production.",
      "Final Plan locked — baseline must be approved by an admin first.",
      "Wrong numbers on Dashboard — confirm the correct week is selected and raw data was pulled recently.",
    ],
    tip: "For technical setup (env vars, deploy, backups), see DEPLOY.md and OPS_RUNBOOK.md in the repository. Admins can see environment status under Settings → About.",
  },
  {
    id: "getting-help",
    title: "Getting help",
    paragraphs: [
      "For access or passwords: contact your Planning Suite administrator (Settings → Users).",
      "For pipeline failures: note the time, page, and any error text. Admins can check server logs using the request ID shown in API errors.",
      "For business logic questions (how baseline is calculated, sheet ownership): refer to your team’s planning SOP — this app orchestrates existing scripts and sheets.",
    ],
  },
];

export const QUICK_LINKS = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Auto-Pilot", href: "/autopilot", roles: ["admin", "planner"] },
  { label: "Manual Baseline", href: "/baseline/load-raw", roles: ["admin", "planner"] },
  { label: "Product Launch", href: "/new-product-launch", roles: ["admin", "planner"] },
  { label: "Settings", href: "/settings" },
] as const;
