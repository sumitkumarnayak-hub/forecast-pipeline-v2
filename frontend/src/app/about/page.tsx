"use client";

import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { useAuth } from "@/hooks/useAuth";
import {
  GUIDE_INTRO,
  GUIDE_SECTIONS,
  QUICK_LINKS,
} from "@/lib/userGuide";
import {
  BookOpen,
  ArrowRight,
  Lightbulb,
  ExternalLink,
  ChevronRight,
} from "lucide-react";

export default function AboutPage() {
  const { role } = useAuth();

  const visibleQuickLinks = QUICK_LINKS.filter(
    link => !("roles" in link) || !link.roles || link.roles.includes(role || "viewer"),
  );

  return (
    <AppShell
      title="About & User Guide"
      subtitle="How to use Planning Suite — written for new team members"
    >
      <div className="guide-layout">
        <aside className="guide-toc card">
          <div className="guide-toc-header">
            <BookOpen size={18} />
            <span>On this page</span>
          </div>
          <nav aria-label="Guide sections">
            {GUIDE_SECTIONS.map(section => (
              <a key={section.id} href={`#${section.id}`} className="guide-toc-link">
                <ChevronRight size={14} />
                {section.title}
              </a>
            ))}
          </nav>
          <div className="guide-toc-footer">
            <span className="text-xs text-muted">Version {GUIDE_INTRO.version}</span>
          </div>
        </aside>

        <div className="guide-main">
          <section className="card guide-hero">
            <h2 className="guide-hero-title">{GUIDE_INTRO.title}</h2>
            <p className="guide-hero-sub">{GUIDE_INTRO.subtitle}</p>
            <div className="guide-quick-links">
              {visibleQuickLinks.map(link => (
                <Link key={link.href} href={link.href} className="guide-quick-pill">
                  {link.label}
                  <ArrowRight size={13} />
                </Link>
              ))}
            </div>
          </section>

          {GUIDE_SECTIONS.map(section => (
            <section key={section.id} id={section.id} className="card guide-section">
              <h3 className="guide-section-title">{section.title}</h3>

              {section.paragraphs?.map((p, i) => (
                <p key={i} className="guide-p">
                  {p}
                </p>
              ))}

              {section.bullets && (
                <ul className="guide-ul">
                  {section.bullets.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              )}

              {section.steps && (
                <ol className="guide-steps">
                  {section.steps.map((step, i) => (
                    <li key={i} className="guide-step">
                      <div className="guide-step-title">{step.title}</div>
                      <div className="guide-step-body">{step.body}</div>
                    </li>
                  ))}
                </ol>
              )}

              {section.table && (
                <div className="table-wrap guide-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        {section.table.headers.map(h => (
                          <th key={h}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {section.table.rows.map((row, ri) => (
                        <tr key={ri}>
                          {row.map((cell, ci) => (
                            <td key={ci} style={{ fontSize: "0.82rem", verticalAlign: "top" }}>
                              {cell}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {section.tip && (
                <div className="alert alert-info guide-tip">
                  <Lightbulb size={16} style={{ flexShrink: 0, marginTop: 2 }} />
                  <span>{section.tip}</span>
                </div>
              )}
            </section>
          ))}

          <section className="card guide-section">
            <h3 className="guide-section-title">More for administrators</h3>
            <p className="guide-p">
              Environment checks, SMTP status, and database info live under{" "}
              <Link href="/settings">Settings</Link> → About tab.
              Deployment and backup procedures are documented in the repository:
            </p>
            <ul className="guide-ul">
              <li>
                <code>DEPLOY.md</code> — production deployment (Vercel + Render)
              </li>
              <li>
                <code>OPS_RUNBOOK.md</code> — incidents, logs, restarts
              </li>
              <li>
                <code>DATA_SOURCES.md</code> — where data is stored
              </li>
            </ul>
            <p className="guide-p text-sm text-muted" style={{ marginBottom: 0 }}>
              <ExternalLink size={13} style={{ display: "inline", verticalAlign: "middle" }} />{" "}
              These files ship with the codebase for your ops team.
            </p>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
