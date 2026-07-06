"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { prefetchRoute } from "@/lib/pagePrefetch";
import { homePathForRole } from "@/lib/navigation";

export default function LoginPage() {
  const router = useRouter();
  const { establishSession, user, hydrated } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (hydrated && user) {
      router.replace(homePathForRole(user.role));
    }
  }, [hydrated, user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError("Please enter both username and password.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const { data } = await api.post("/api/auth/login", {
        username: username.trim(),
        password,
        remember_me: rememberMe,
      });
      if (!data?.user) {
        setError("Login succeeded but no user profile was returned. Check backend logs.");
        return;
      }
      establishSession(data.user);
      const home = homePathForRole(data.user.role);
      router.replace(home);
      prefetchRoute(home);
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string }; status?: number }; message?: string };
      const detail = ax?.response?.data?.detail;
      if (detail) {
        setError(typeof detail === "string" ? detail : JSON.stringify(detail));
      } else if (!ax?.response) {
        setError("Cannot reach the API server. Check that the backend is running and BACKEND_URL is set on Vercel.");
      } else {
        setError("Invalid username or password.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card animate-fade-in">
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 52, height: 52, borderRadius: 14, background: "var(--blue-dim)", border: "1px solid var(--border-accent)", marginBottom: "1rem", fontSize: "1.5rem" }}>📊</div>
          <div style={{ fontSize: "0.62rem", fontWeight: 700, letterSpacing: "0.2em", textTransform: "uppercase", color: "var(--blue)", marginBottom: "0.4rem" }}>Demand Planning</div>
          <div style={{ fontSize: "1.55rem", fontWeight: 800, letterSpacing: "-0.03em", color: "var(--text-primary)" }}>Planning Suite</div>
          <div style={{ fontSize: "0.82rem", color: "var(--text-secondary)", marginTop: "0.3rem" }}>Sign in to your account</div>
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: "1rem" }}>⚠️ {error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label" htmlFor="username">Username</label>
            <input
              id="username"
              className="form-input"
              type="text"
              placeholder="Enter your username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoFocus
              autoComplete="username"
              disabled={loading}
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="password">Password</label>
            <div className="password-input-wrap">
              <input
                id="password"
                className="form-input password-input"
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                disabled={loading}
              />
              <button
                type="button"
                className="password-toggle-btn"
                onClick={() => setShowPassword(v => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2" style={{ marginBottom: "1.25rem" }}>
            <input type="checkbox" id="rem" checked={rememberMe} onChange={e => setRememberMe(e.target.checked)} disabled={loading} style={{ accentColor: "var(--blue)", width: 14, height: 14, cursor: "pointer" }} />
            <label htmlFor="rem" style={{ fontSize: "0.8rem", color: "var(--text-secondary)", cursor: "pointer" }}>Keep me signed in</label>
          </div>
          <button type="submit" className="btn btn-primary w-full btn-lg" disabled={loading}>
            {loading ? <><span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />  Signing in…</> : "Sign In"}
          </button>
        </form>

        <div style={{ marginTop: "1.25rem", padding: "0.75rem 1rem", background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.3)", borderRadius: "var(--radius-md)", fontSize: "0.75rem", color: "#fcd34d" }}>
          <div style={{ fontWeight: 600, marginBottom: "0.2rem" }}>Development mode</div>
          Default logins: <code style={{ background: "rgba(255,255,255,0.08)", padding: "0 4px", borderRadius: 3 }}>admin / admin123</code>{" "}
          · <code style={{ background: "rgba(255,255,255,0.08)", padding: "0 4px", borderRadius: 3 }}>planner / planner123</code>{" "}
          · <code style={{ background: "rgba(255,255,255,0.08)", padding: "0 4px", borderRadius: 3 }}>viewer / viewer123</code>
        </div>
      </div>
    </div>
  );
}
