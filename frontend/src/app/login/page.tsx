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
  const [email, setEmail] = useState("");
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
    if (!email.trim() || !password) {
      setError("Please enter both email and password.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const { data } = await api.post("/api/auth/login", {
        email: email.trim(),
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
    <div className="login-page" style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      minHeight: "100vh",
      background: "radial-gradient(circle at 10% 20%, rgba(26, 32, 53, 1) 0%, rgba(11, 15, 26, 1) 90%)",
      fontFamily: "'Outfit', 'Inter', sans-serif",
      position: "relative",
      overflow: "hidden"
    }}>
      {/* Dynamic Background Glowing Orbs */}
      <div style={{ position: "absolute", width: "400px", height: "400px", background: "radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, rgba(0,0,0,0) 70%)", top: "-100px", left: "-100px", borderRadius: "50%", pointerEvents: "none" }} />
      <div style={{ position: "absolute", width: "500px", height: "500px", background: "radial-gradient(circle, rgba(16, 185, 129, 0.1) 0%, rgba(0,0,0,0) 70%)", bottom: "-150px", right: "-150px", borderRadius: "50%", pointerEvents: "none" }} />

      <div className="login-card animate-fade-in" style={{
        background: "rgba(22, 28, 45, 0.65)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        borderRadius: "24px",
        padding: "3rem 2.5rem",
        width: "100%",
        maxWidth: "440px",
        boxShadow: "0 20px 40px rgba(0, 0, 0, 0.3)",
        position: "relative",
        zIndex: 10
      }}>
        <div style={{ textAlign: "center", marginBottom: "2.5rem" }}>
          <div style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 60,
            height: 60,
            borderRadius: "18px",
            background: "linear-gradient(135deg, rgba(99, 102, 241, 0.2) 0%, rgba(99, 102, 241, 0.05) 100%)",
            border: "1px solid rgba(99, 102, 241, 0.3)",
            boxShadow: "0 8px 16px rgba(99, 102, 241, 0.15)",
            marginBottom: "1.25rem",
            fontSize: "1.75rem"
          }}>📊</div>
          <div style={{ fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.25em", textTransform: "uppercase", color: "#818cf8", marginBottom: "0.5rem" }}>Demand Planning</div>
          <div style={{ fontSize: "1.95rem", fontWeight: 800, letterSpacing: "-0.03em", color: "#ffffff", background: "linear-gradient(to right, #ffffff, #c7d2fe)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>Planning Suite</div>
          <div style={{ fontSize: "0.88rem", color: "#94a3b8", marginTop: "0.4rem" }}>Sign in to orchestrate forecasts</div>
        </div>

        {error && (
          <div className="alert alert-danger" style={{
            marginBottom: "1.5rem",
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.2)",
            color: "#fca5a5",
            borderRadius: "12px",
            padding: "0.75rem 1rem",
            fontSize: "0.8rem",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem"
          }}>
            <span>⚠️</span>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group" style={{ marginBottom: "1.25rem" }}>
            <label className="form-label" htmlFor="email" style={{ color: "#cbd5e1", fontSize: "0.82rem", fontWeight: 500, marginBottom: "0.4rem", display: "block" }}>Email</label>
            <input
              id="email"
              className="form-input"
              type="email"
              placeholder="Enter your email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              autoFocus
              autoComplete="email"
              disabled={loading}
              style={{
                background: "rgba(15, 23, 42, 0.6)",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                borderRadius: "12px",
                color: "#ffffff",
                padding: "0.75rem 1rem",
                width: "100%",
                fontSize: "0.88rem"
              }}
            />
          </div>
          <div className="form-group" style={{ marginBottom: "1.5rem" }}>
            <label className="form-label" htmlFor="password" style={{ color: "#cbd5e1", fontSize: "0.82rem", fontWeight: 500, marginBottom: "0.4rem", display: "block" }}>Password</label>
            <div className="password-input-wrap" style={{ position: "relative" }}>
              <input
                id="password"
                className="form-input password-input"
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                disabled={loading}
                style={{
                  background: "rgba(15, 23, 42, 0.6)",
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                  borderRadius: "12px",
                  color: "#ffffff",
                  padding: "0.75rem 1rem",
                  paddingRight: "2.5rem",
                  width: "100%",
                  fontSize: "0.88rem"
                }}
              />
              <button
                type="button"
                className="password-toggle-btn"
                onClick={() => setShowPassword(v => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                tabIndex={-1}
                style={{
                  position: "absolute",
                  right: "10px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  color: "#94a3b8",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center"
                }}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2" style={{ marginBottom: "1.75rem" }}>
            <input
              type="checkbox"
              id="rem"
              checked={rememberMe}
              onChange={e => setRememberMe(e.target.checked)}
              disabled={loading}
              style={{ accentColor: "#6366f1", width: 14, height: 14, cursor: "pointer" }}
            />
            <label htmlFor="rem" style={{ fontSize: "0.8rem", color: "#94a3b8", cursor: "pointer", userSelect: "none" }}>Keep me signed in</label>
          </div>
          <button
            type="submit"
            className="btn btn-primary w-full"
            disabled={loading}
            style={{
              background: "linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)",
              border: "none",
              borderRadius: "12px",
              color: "#ffffff",
              padding: "0.8rem",
              fontWeight: 600,
              fontSize: "0.92rem",
              boxShadow: "0 4px 12px rgba(99, 102, 241, 0.3)",
              cursor: "pointer",
              transition: "transform 0.1s, opacity 0.15s"
            }}
            onMouseDown={e => e.currentTarget.style.transform = "scale(0.98)"}
            onMouseUp={e => e.currentTarget.style.transform = "scale(1)"}
          >
            {loading ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem" }}>
                <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                Signing in…
              </div>
            ) : "Sign In"}
          </button>
        </form>

        <div style={{
          marginTop: "1.75rem",
          padding: "1rem 1.25rem",
          background: "rgba(30, 41, 59, 0.5)",
          border: "1px solid rgba(255, 255, 255, 0.05)",
          borderRadius: "14px",
          fontSize: "0.78rem",
          color: "#94a3b8",
          lineHeight: 1.5
        }}>
          <div style={{ fontWeight: 700, color: "#fcd34d", marginBottom: "0.35rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
            <span>🛠️</span> Development Mode Credentials
          </div>
          <div style={{ fontSize: "0.74rem" }}>
            <span style={{ color: "#cbd5e1" }}>Admin:</span> <code style={{ color: "#cbd5e1", background: "rgba(255,255,255,0.06)", padding: "2px 6px", borderRadius: 4, fontFamily: "monospace" }}>sumitkumar.nayak@licious.com / admin123</code>
          </div>
        </div>
      </div>
    </div>
  );
}
