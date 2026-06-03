"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import { LogOut, GitPullRequest, Code2 } from "lucide-react";

export default function DashboardPage() {
  const router = useRouter();
  const { user, logout, loadMe, loading } = useAuthStore();

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
      </main>
    </div>
  );
}
