import React, { createContext, useCallback, useContext, useEffect, useReducer } from "react";
import type { User } from "../types";
import * as api from "../api/client";

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  refreshTokenStr: string | null;
}

type AuthAction =
  | { type: "LOGIN"; user: User; refreshToken: string }
  | { type: "LOGOUT" }
  | { type: "LOADING"; loading: boolean }
  | { type: "SET_USER"; user: User };

function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case "LOGIN":
      return { ...state, user: action.user, refreshTokenStr: action.refreshToken, isAuthenticated: true, isLoading: false };
    case "LOGOUT":
      return { ...state, user: null, refreshTokenStr: null, isAuthenticated: false, isLoading: false };
    case "LOADING":
      return { ...state, isLoading: action.loading };
    case "SET_USER":
      return { ...state, user: action.user, isAuthenticated: true };
    default:
      return state;
  }
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, displayName?: string) => Promise<void>;
  joinWithInvite: (token: string, username: string, displayName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(authReducer, {
    user: null,
    isAuthenticated: false,
    isLoading: true,
    refreshTokenStr: localStorage.getItem("workbench_refresh_token"),
  });

  const handleAuthSuccess = useCallback((data: { access_token: string; refresh_token: string; user: User }) => {
    api.setAuthToken(data.access_token);
    localStorage.setItem("workbench_refresh_token", data.refresh_token);
    dispatch({ type: "LOGIN", user: data.user, refreshToken: data.refresh_token });
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const data = await api.login(username, password);
    handleAuthSuccess(data);
  }, [handleAuthSuccess]);

  const register = useCallback(async (username: string, password: string, displayName?: string) => {
    const data = await api.register(username, password, displayName);
    handleAuthSuccess(data);
  }, [handleAuthSuccess]);

  const joinWithInvite = useCallback(async (token: string, username: string, displayName?: string) => {
    const data = await api.joinWithInvite(token, username, displayName);
    handleAuthSuccess(data);
  }, [handleAuthSuccess]);

  const logout = useCallback(() => {
    api.setAuthToken(null);
    localStorage.removeItem("workbench_refresh_token");
    dispatch({ type: "LOGOUT" });
  }, []);

  // Try to restore session on mount
  useEffect(() => {
    const token = api.getAuthToken();
    if (token) {
      api.getMe()
        .then((user) => dispatch({ type: "SET_USER", user }))
        .catch(() => {
          // Try refresh
          const refreshTokenStr = localStorage.getItem("workbench_refresh_token");
          if (refreshTokenStr) {
            api.refreshToken(refreshTokenStr)
              .then((data) => handleAuthSuccess(data))
              .catch(() => {
                api.setAuthToken(null);
                localStorage.removeItem("workbench_refresh_token");
                dispatch({ type: "LOGOUT" });
              });
          } else {
            dispatch({ type: "LOGOUT" });
          }
        })
        .finally(() => dispatch({ type: "LOADING", loading: false }));
    } else {
      dispatch({ type: "LOADING", loading: false });
    }
  }, [handleAuthSuccess]);

  return (
    <AuthContext.Provider value={{ ...state, login, register, joinWithInvite, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
