/**
 * In-app user guide for Planning Suite — focused on Product Launch, Hub Launch, and Settings.
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
  title: "Planning Suite — Scoped Deployment Guide",
  subtitle:
    "A walkthrough of the scoped planning tool focused exclusively on New Product Launch, Hub Launch, and Settings. Other modules are currently marked as 'Coming Soon'.",
  version: "3.0 (Scoped)",
};

export const GUIDE_SECTIONS: GuideSection[] = [
  {
    id: "what-is-this",
    title: "What is this Scoped Deployment?",
    paragraphs: [
      "This deployment of the Planning Suite focuses on managing the product and location lifecycle: executing new product launches, expanding products to new segments, managing old SKU replacements, and cloning hub mappings.",
      "Most backend logic reads and writes data directly to cached Google Sheets (such as the Submission_Log, P-H Master, and Hub Mapping tables). This app serves as your operational control panel.",
      "Other forecasting pipeline modules (Dashboard, Auto-Pilot, Baseline, and Final Plan) are disabled and display a 'Coming Soon' screen in this release.",
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
          "Everything: approve/reject launches, manage users & email alerts, clone hub mappings, edit settings",
        ],
        [
          "Planner",
          "Demand planner",
          "Run product launches (New Launch, Expansion, Replacement), preview cloning, update personal preferences",
        ],
        [
          "Product",
          "Product Manager",
          "Draft and submit new product launches, expansions, and replacement mappings for admin approval",
        ],
        [
          "Viewer",
          "Stakeholder",
          "Read-only access to Settings and history logs — cannot submit files or approve mappings",
        ],
      ],
    },
    tip: "If a button is missing or a page says “access denied”, ask an admin to check your role under Settings → Users.",
  },
  {
    id: "npl-flow",
    title: "Product Launch Workflow",
    paragraphs: [
      "The Product Launch module manages adding, expanding, or replacing SKUs in your forecasting system using a structured 4-stage wizard.",
    ],
    steps: [
      {
        title: "1. Pick Launch Type",
        body: "Choose between 'New Product Launch' (first-time SKU introduction), 'Product Expansion' (expanding existing SKUs to new cities/hubs), or 'Product Replacement' (swapping an old SKU with a new one at a defined split percentage).",
      },
      {
        title: "2. Download and Fill Template",
        body: "Select target cities or hubs and download the pre-formatted Excel template. Fill in the volume allocations. All fields are mandatory and strictly typed; ensure numeric columns (MRP, allocations, shelf life) do not contain text.",
      },
      {
        title: "3. Parse and Review Split",
        body: "Upload the filled Excel template. The system validates formatting and parses it. Review the hub-level splits and adjust values directly in the editable grid if necessary.",
      },
      {
        title: "4. Set Launch Date & Submit",
        body: "Select a valid Monday launch date (must satisfy the T+4 weeks rule). Click Submit to push the changes. The data is validated for duplicates and synchronized with the Google Sheets Submission_Log.",
      },
    ],
  },
  {
    id: "hub-launch-flow",
    title: "Hub Launch Mappings",
    paragraphs: [
      "The Hub Launch page is used to map new or restructured hubs by cloning SKU mappings from existing reference 'source' hubs. This ensures instant setup of inventory buffers and sales channels for new hub sites.",
    ],
    steps: [
      {
        title: "1. Select Targets",
        body: "Choose the target city and the new hub you want to configure. Select the reference source hub whose SKU structures you wish to copy.",
      },
      {
        title: "2. Clone Mappings",
        body: "Run the cloning tool to generate proposed SKU mappings for the new hub on the backend. Review the preview list.",
      },
      {
        title: "3. Commit to Sheet",
        body: "Confirm and submit the proposed clones. The mapping records will be appended to the Google Sheet Hub Mapping configuration table.",
      },
    ],
  },
  {
    id: "pages",
    title: "Page-by-page guide",
    bullets: [
      "Product Launch — Scoped wizard for drafting, parsing, and submitting launches (New Launch, Expansion, Replacement) plus a Submission History tab to track approval workflows.",
      "Hub Launch — Self-contained page to clone SKU mappings from reference source hubs.",
      "Settings — Profile configuration. Admins can manage users, adjust email notification lists, trigger test SMTP alerts, and audit system sessions.",
      "Dashboard, Auto-Pilot, Baseline, Final Plan, Validation, Analytics — Disabled for this release (displaying 'Coming Soon').",
    ],
  },
  {
    id: "tips",
    title: "Tips & troubleshooting",
    bullets: [
      "All template upload fields are mandatory: If any cells or columns are left blank, the upload parser will show validation errors.",
      "Strict data type checks: Allocations and price values must be numeric. Text values in number fields will reject the file.",
      "Launch Date rules: Launch dates must fall on a Monday and must be at least T+4 weeks in the future.",
      "Cache Status: In Settings → About, admins can monitor the TTL status of Google Sheets caches (e.g. P-L Master, Hub Mapping). These caches refresh automatically every 30 minutes, or can be force-refreshed.",
    ],
  },
];

export const QUICK_LINKS = [
  { label: "Product Launch", href: "/new-product-launch", roles: ["admin", "planner", "product"] },
  { label: "Hub Launch", href: "/hub-launch", roles: ["admin", "planner", "product"] },
  { label: "Settings", href: "/settings" },
] as const;
