import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
  withCredentials: true,
});

// ── Token storage (in-memory for SSR safety) ──────────────────────────────
let _accessToken: string | null = null;
let _refreshToken: string | null = null;

export const tokenStore = {
  set(access: string, refresh: string) {
    _accessToken = access;
    _refreshToken = refresh;
    if (typeof window !== "undefined") {
      localStorage.setItem("access_token", access);
      localStorage.setItem("refresh_token", refresh);
    }
  },
  load() {
    if (typeof window !== "undefined") {
      _accessToken = localStorage.getItem("access_token");
      _refreshToken = localStorage.getItem("refresh_token");
    }
  },
  clear() {
    _accessToken = null;
    _refreshToken = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
  },
  get access() { return _accessToken; },
  get refresh() { return _refreshToken; },
};

// ── Request interceptor — attach Bearer token ────────────────────────────
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  tokenStore.load();
  if (_accessToken) {
    config.headers.Authorization = `Bearer ${_accessToken}`;
  }
  return config;
});

// ── Response interceptor — auto-refresh on 401 ──────────────────────────
let refreshing = false;
let waiters: ((token: string) => void)[] = [];

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }
    original._retry = true;

    if (refreshing) {
      return new Promise((resolve) => {
        waiters.push((token) => {
          original.headers.Authorization = `Bearer ${token}`;
          resolve(api(original));
        });
      });
    }

    refreshing = true;
    try {
      const { data } = await axios.post(`${API_URL}/api/v1/auth/refresh`, {
        refresh_token: _refreshToken,
      });
      tokenStore.set(data.access_token, data.refresh_token);
      waiters.forEach((cb) => cb(data.access_token));
      waiters = [];
      original.headers.Authorization = `Bearer ${data.access_token}`;
      return api(original);
    } catch {
      tokenStore.clear();
      window.location.href = "/auth/login";
      return Promise.reject(error);
    } finally {
      refreshing = false;
    }
  }
);

// ── Auth API calls ────────────────────────────────────────────────────────
export const authApi = {
  register: (email: string, username: string, password: string) =>
    api.post("/auth/register", { email, username, password }),

  login: (email: string, password: string) =>
    api.post("/auth/login", { email, password }),

  me: () => api.get("/auth/me"),

  githubLogin: () => {
    window.location.href = `${API_URL}/api/v1/auth/github`;
  },

  githubTokenExchange: (code: string) =>
    api.post("/auth/github/token", { code }),
};
