"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, Mail, Lock, ShieldAlert, Sparkles } from "lucide-react";
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
    <div className="relative flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 via-slate-100 to-indigo-50/30 p-6 overflow-hidden font-sans">
      {/* Background blobs */}
      <div className="absolute -top-[10%] -left-[10%] w-[350px] h-[350px] rounded-full bg-indigo-400/5 blur-[80px] pointer-events-none" />
      <div className="absolute -bottom-[10%] -right-[10%] w-[350px] h-[350px] rounded-full bg-purple-400/5 blur-[80px] pointer-events-none" />

      <div className="relative w-full max-w-[400px] rounded-3xl bg-white/45 backdrop-blur-2xl border border-white/60 p-10 shadow-[0_8px_32px_0_rgba(31,38,135,0.04)] box-border">
        {/* Logo/Icon */}
        <div className="text-center mb-8">
          <h2 className="text-2xl font-semibold tracking-tight text-slate-900">Planning Suite</h2>
          <p className="text-xs text-slate-500 mt-1">Demand Planning Platform</p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="flex items-center gap-2 mb-5 rounded-xl border border-red-100 bg-red-50/50 p-3 text-xs text-red-700">
            <ShieldAlert className="w-4 h-4 text-red-500 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          {/* Email input */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-xs font-semibold text-slate-600 px-0.5">
              Email Address
            </label>
            <div className="relative">
              <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400">
                <Mail className="w-4 h-4" />
              </span>
              <input
                id="email"
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                autoFocus
                autoComplete="email"
                disabled={loading}
                className="w-full bg-white/60 border border-slate-200 rounded-xl py-2.5 pl-10 pr-4 text-sm text-slate-900 placeholder:text-slate-400 outline-none transition-all focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 disabled:opacity-50"
              />
            </div>
          </div>

          {/* Password input */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-xs font-semibold text-slate-600 px-0.5">
              Password
            </label>
            <div className="relative">
              <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400">
                <Lock className="w-4 h-4" />
              </span>
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
                disabled={loading}
                className="w-full bg-white/60 border border-slate-200 rounded-xl py-2.5 pl-10 pr-11 text-sm text-slate-900 placeholder:text-slate-400 outline-none transition-all focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => setShowPassword(v => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                tabIndex={-1}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
              >
                {showPassword ? <EyeOff className="w-4.5 h-4.5" /> : <Eye className="w-4.5 h-4.5" />}
              </button>
            </div>
          </div>

          {/* Keep me signed in */}
          <div className="flex items-center gap-2 mt-0.5">
            <input
              type="checkbox"
              id="rem"
              checked={rememberMe}
              onChange={e => setRememberMe(e.target.checked)}
              disabled={loading}
              className="accent-blue-600 w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500/20"
            />
            <label htmlFor="rem" className="text-xs text-slate-600 cursor-pointer select-none">
              Keep me signed in
            </label>
          </div>

          {/* Submit button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white rounded-xl py-2.5 font-medium text-sm transition-all active:scale-[0.98] disabled:opacity-50 shadow-[0_4px_12px_rgba(37,99,235,0.2)] mt-2"
          >
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>

        {/* Development mode indicator */}
        <div className="mt-8 rounded-xl bg-white/40 border border-white/60 p-4 text-[11px] text-slate-500 leading-relaxed shadow-sm">
          <div className="flex items-center gap-1.5 font-semibold text-purple-600 mb-1">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Test Credentials</span>
          </div>
          <code>sumitkumar.nayak@licious.com / admin123</code>
        </div>
      </div>
    </div>
  );
}
