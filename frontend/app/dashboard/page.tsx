"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import { useReviewEvents } from "@/lib/useReviewEvents";
import { LogOut, GitPullRequest, Code2, Radio, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

function timeAgo(ts: number): string {
  const seconds = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ago`;
}

export default function DashboardPage() {
  const router = useRouter();
  const { user, logout, loadMe, loading } = useAuthStore();
  const { events, connected } = useReviewEvents(!!user);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  useEffect(() => {
    if (!loading && !user) router.replace("/auth/login");
  }, [user, loading, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Nav */}
      <nav className="border-b border-gray-200 bg-white px-6 py-3">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-xs font-bold text-white">
              AI
            </div>
            <span className="font-semibold text-gray-900">Code Review</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-500">
              {user.display_name ?? user.username}
            </span>
            <span className="badge bg-brand-100 text-brand-700 capitalize">
              {user.subscription_tier}
            </span>
            <button
              onClick={() => { logout(); router.push("/auth/login"); }}
              className="text-gray-400 hover:text-gray-600"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </nav>

      {/* Content */}
      <main className="mx-auto max-w-7xl px-6 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">
          Welcome, {user.display_name ?? user.username}!
        </h1>
        <p className="text-gray-500 mb-8">Your AI-powered code review dashboard</p>

        {/* Empty state cards */}
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <div className="card text-center py-8">
            <GitPullRequest className="mx-auto h-10 w-10 text-gray-300 mb-3" />
            <p className="font-medium text-gray-700">No pull requests yet</p>
            <p className="text-sm text-gray-400 mt-1">Connect a repo to get started</p>
          </div>
          <div className="card text-center py-8">
            <Code2 className="mx-auto h-10 w-10 text-gray-300 mb-3" />
            <p className="font-medium text-gray-700">No repositories</p>
            <p className="text-sm text-gray-400 mt-1">Install the GitHub webhook</p>
          </div>
          <div className="card">
            <p className="text-sm font-medium text-gray-500 mb-1">Account info</p>
            <p className="text-sm text-gray-700">{user.email}</p>
            <p className="text-xs text-gray-400 mt-1">@{user.username}</p>
            {user.github_id && (
              <p className="mt-2 text-xs text-green-600 font-medium">✓ GitHub connected</p>
            )}
          </div>
        </div>

        {/* Live review activity */}
        <div className="card mt-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Radio className={`h-4 w-4 ${connected ? "text-green-500" : "text-gray-300"}`} />
              <h2 className="font-medium text-gray-900">Live review activity</h2>
            </div>
            <span
              className={`badge ${connected ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}
              data-testid="ws-status"
            >
              {connected ? "Connected" : "Connecting…"}
            </span>
          </div>

          {events.length === 0 ? (
            <p className="py-6 text-center text-sm text-gray-400">
              No activity yet. Review updates will appear here in real time as PRs come in.
            </p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {events.map((event, i) => (
                <li key={i} className="flex items-start gap-3 py-3">
                  {event.type === "review_completed" && (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
                  )}
                  {event.type === "review_failed" && (
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                  )}
                  {event.type === "pr_status" && (
                    <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-brand-500" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-gray-700">
                      {event.type === "pr_status" &&
                        `Reviewing ${event.payload.repo} #${event.payload.pr_number}`}
                      {event.type === "review_completed" &&
                        `Review completed for ${event.payload.repo} #${event.payload.pr_number} — ${event.payload.critical_count} critical, ${event.payload.warning_count} warnings`}
                      {event.type === "review_failed" &&
                        `Review failed for ${event.payload.repo} #${event.payload.pr_number}`}
                    </p>
                    <p className="text-xs text-gray-400">{timeAgo(event.receivedAt)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
    </div>
  );
}
