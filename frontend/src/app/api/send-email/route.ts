import { NextRequest, NextResponse } from "next/server";
import nodemailer from "nodemailer";

export async function POST(req: NextRequest) {
  try {
    const { to, subject, html, secret } = await req.json();

    // Verify secret to authorize request
    const expectedSecret = process.env.AUTH_SECRET_KEY || "dev-insecure-auth-key-change-before-production";
    if (secret !== expectedSecret) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const smtpUser = process.env.FROM_EMAIL || process.env.SMTP_USER;
    const smtpPassword = process.env.FROM_EMAIL_APP_PASSWORD || process.env.SMTP_PASSWORD;

    if (!smtpUser || !smtpPassword) {
      return NextResponse.json(
        { error: "SMTP credentials not configured on frontend server" },
        { status: 500 }
      );
    }

    const transporter = nodemailer.createTransport({
      host: "smtp.gmail.com",
      port: 587,
      secure: false,
      auth: {
        user: smtpUser,
        pass: smtpPassword,
      },
    });

    const info = await transporter.sendMail({
      from: `"Planning workbench" <${smtpUser}>`,
      to: Array.isArray(to) ? to.join(", ") : to,
      subject: subject,
      html: html,
    });

    return NextResponse.json({ ok: true, messageId: info.messageId });
  } catch (error: any) {
    console.error("Nodemailer send failed:", error);
    return NextResponse.json({ error: error.message || "Failed to send email" }, { status: 500 });
  }
}
