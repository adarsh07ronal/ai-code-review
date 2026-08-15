import { create } from "zustand";
import { authApi, tokenStore } from "@/lib/api";

interface User {
  id: number;
  email: string;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  subscription_tier: "free" | "pro" | "team";
  github_id: number | null;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  checked: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<void>;
  logout: () => void;
  loadMe: () => Promise<void>;
  setTokensAndUser: (access: string, refresh: string, user: User) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: false,
  // Distinguishes "haven't checked auth yet" from "checked, no user" — pages
  // use this to avoid redirecting to login before loadMe() has resolved.
  checked: false,

  login: async (email, password) => {
    set({ loading: true });
    try {
      const { data } = await authApi.login(email, password);
      tokenStore.set(data.access_token, data.refresh_token);
      set({ user: data.user, loading: false });
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  register: async (email, username, password) => {
    set({ loading: true });
    try {
      const { data } = await authApi.register(email, username, password);
      tokenStore.set(data.access_token, data.refresh_token);
      set({ user: data.user, loading: false });
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  logout: () => {
    tokenStore.clear();
    set({ user: null });
  },

  loadMe: async () => {
    tokenStore.load();
    if (!tokenStore.access) {
      set({ checked: true });
      return;
    }
    set({ loading: true });
    try {
      const { data } = await authApi.me();
      set({ user: data, loading: false, checked: true });
    } catch {
      tokenStore.clear();
      set({ user: null, loading: false, checked: true });
    }
  },

  setTokensAndUser: (access, refresh, user) => {
    tokenStore.set(access, refresh);
    set({ user });
  },
}));
