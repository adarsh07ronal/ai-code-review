"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Check, Loader2 } from "lucide-react";
import { useAuthStore } from "@/lib/store";
import { billingApi } from "@/lib/api";

const PLANS = [
  {
    tier: "free" as const,
    name: "Free",
    price: "$0",
    features: ["1 repository", "Community support"],
  },
  {
    tier: "pro" as const,
    name: "Pro",
    price: "$19/mo",
    features: ["Unlimited repositories", "Priority review queue", "Email support"],
  },
  {
    tier: "team" as const,
    name: "Team",
    price: "$49/mo",
    features: ["Everything in Pro", "Organizations & role-based access", "Shared team dashboard"],
  },
];

export default function BillingPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loadMe, loading, checked } = useAuthStore();
  const [pendingTier, setPendingTier] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  useEffect(() => {
    if (checked && !user) router.replace("/auth/login");
  }, [user, checked, router]);

  const checkoutResult = searchParams.get("checkout");

  const handleUpgrade = async (tier: "pro" | "team") => {
    setError("");
    setPendingTier(tier);
    try {
      const { data } = await billingApi.checkout(tier);
      window.location.href = data.checkout_url;
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Could not start checkout. Please try again.");
      setPendingTier(null);
    }
  };

  const handleManageBilling = async () => {
    setError("");
    setPortalLoading(true);
    try {
      const { data } = await billingApi.portal();
      window.location.href = data.portal_url;
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Could not open billing portal.");
      setPortalLoading(false);
    }
  };

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="border-b border-gray-200 bg-white px-6 py-3">
        <div className="mx-auto flex max-w-7xl items-center gap-4">
          <Link href="/dashboard" className="text-gray-400 hover:text-gray-600">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <span className="font-semibold text-gray-900">Billing</span>
        </div>
      </nav>

      <main className="mx-auto max-w-5xl px-6 py-8">
        {checkoutResult === "success" && (
          <div className="mb-6 rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-700">
            Subscription updated! It may take a few seconds to reflect below.
          </div>
        )}
        {checkoutResult === "cancelled" && (
          <div className="mb-6 rounded-lg bg-gray-100 border border-gray-200 px-4 py-3 text-sm text-gray-600">
            Checkout was cancelled.
          </div>
        )}
        {error && (
          <div className="mb-6 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Plan &amp; billing</h1>
            <p className="text-gray-500">
              Current plan:{" "}
              <span className="badge bg-brand-100 text-brand-700 capitalize">{user.subscription_tier}</span>
            </p>
          </div>
          {user.subscription_tier !== "free" && (
            <button onClick={handleManageBilling} className="btn-secondary" disabled={portalLoading}>
              {portalLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Manage billing
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {PLANS.map((plan) => {
            const isCurrent = user.subscription_tier === plan.tier;
            return (
              <div key={plan.tier} className="card flex flex-col">
                <h2 className="text-lg font-semibold text-gray-900">{plan.name}</h2>
                <p className="mt-1 text-2xl font-bold text-gray-900">{plan.price}</p>
                <ul className="mt-4 flex-1 space-y-2">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-gray-600">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
                      {f}
                    </li>
                  ))}
                </ul>
                {plan.tier === "free" ? (
                  <button className="btn-secondary mt-6" disabled>
                    {isCurrent ? "Current plan" : "Free"}
                  </button>
                ) : (
                  <button
                    onClick={() => handleUpgrade(plan.tier)}
                    className="btn-primary mt-6"
                    disabled={isCurrent || pendingTier !== null}
                  >
                    {pendingTier === plan.tier ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    {isCurrent ? "Current plan" : `Upgrade to ${plan.name}`}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </main>
    </div>
  );
}
