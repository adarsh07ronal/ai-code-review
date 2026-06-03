"use client";
import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuthStore } from "@/lib/store";
import { authApi, tokenStore } from "@/lib/api";

export default function AuthCallbackPage() {
  const router = useRouter();
  const params = useSearchParams();
  const { setTokensAndUser } = useAuthStore();

  useEffect(() => {
    const access = params.get("access_token");
    const refresh = params.get("refresh_token");

    if (access && refresh) {
      // Backend redirect flow — tokens in URL params
      tokenStore.set(access, refresh);
      authApi.me().then(({ data }) => {
        setTokensAndUser(access, refresh, data);
        router.replace("/dashboard");
      }).catch(() => router.replace("/auth/login"));
    } else {
      // No tokens — something went wrong
      router.replace("/auth/login?error=oauth_failed");
    }
  }, [params, router, setTokensAndUser]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <Loader2 className="mx-auto h-8 w-8 animate-spin text-brand-600" />
        <p className="mt-3 text-sm text-gray-500">Signing you in…</p>
      </div>
    </div>
  );
}
