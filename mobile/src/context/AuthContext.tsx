import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { getApiUrl } from '../config';
import { setAuthToken } from '../utils/authFetch';

export type AuthStatus = 'loading' | 'anonymous' | 'authenticated' | 'demo';

export interface AuthUser {
  username: string;
  role: string;
}

interface StoredSession {
  token: string;
  user: AuthUser;
  expiresAt: number;
}

interface AuthContextType {
  status:    AuthStatus;
  token:     string | null;
  user:      AuthUser | null;
  isDemo:    boolean;
  login:     (username: string, password: string) => Promise<{ ok: boolean; error?: string; retryAfter?: number }>;
  logout:    () => void;
  enterDemo: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth debe usarse dentro de AuthProvider');
  return ctx;
};

// ── Persistencia (RNFS, mismo patrón tolerante que DroneContext) ─────────────
const AUTH_FILE = 'auth.json';
const _fs = () => {
  try {
    return require('react-native-fs');
  } catch {
    return null;
  }
};

const getStoredSession = async (): Promise<StoredSession | null> => {
  const RNFS = _fs();
  if (!RNFS) return null;
  try {
    const dir = `${RNFS.DocumentDirectoryPath}/GCS`;
    const path = `${dir}/${AUTH_FILE}`;
    const exists = await RNFS.exists(path);
    if (!exists) return null;
    const data = await RNFS.readFile(path, 'utf8');
    const parsed = JSON.parse(data);
    if (!parsed?.token || !parsed?.user) return null;
    return parsed as StoredSession;
  } catch {
    return null;
  }
};

const persistSession = async (session: StoredSession | null) => {
  const RNFS = _fs();
  if (!RNFS) return;
  try {
    const dir = `${RNFS.DocumentDirectoryPath}/GCS`;
    const exists = await RNFS.exists(dir);
    if (!exists) await RNFS.mkdir(dir);
    const path = `${dir}/${AUTH_FILE}`;
    if (session === null) {
      if (await RNFS.exists(path)) await RNFS.unlink(path);
      return;
    }
    await RNFS.writeFile(path, JSON.stringify(session), 'utf8');
  } catch { /* fallback silencioso */ }
};

// ── Provider ─────────────────────────────────────────────────────────────────

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const sessionRef = useRef<StoredSession | null>(null);

  useEffect(() => { setAuthToken(token); }, [token]);

  const applySession = useCallback((session: StoredSession | null) => {
    sessionRef.current = session;
    if (session && session.expiresAt > Date.now() / 1000) {
      setToken(session.token);
      setUser(session.user);
      setStatus('authenticated');
    } else {
      setToken(null);
      setUser(null);
      setStatus('anonymous');
    }
  }, []);

  // Al montar: cargar sesión guardada y validarla contra el backend
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const stored = await getStoredSession();
      if (cancelled) return;
      if (!stored || stored.expiresAt <= Date.now() / 1000) {
        if (stored) await persistSession(null);
        applySession(null);
        return;
      }
      // Validar contra el backend (caja negra: token debe seguir siendo válido)
      try {
        const res = await fetch(`${getApiUrl()}/api/auth/me`, {
          headers: { Authorization: `Bearer ${stored.token}` },
        });
        if (res.status === 200) {
          const body = await res.json();
          const me = body?.user;
          if (me?.username) {
            applySession({ ...stored, user: { username: me.username, role: me.role ?? 'operator' } });
            return;
          }
        }
        await persistSession(null);
        applySession(null);
      } catch {
        // Backend no responde: se mantiene la sesión local pero se deja pasar
        // al login; el usuario podrá reconectar cuando vuelva el servidor.
        applySession(stored);
      }
    })();
    return () => { cancelled = true; };
  }, [applySession]);

  const login = useCallback(async (username: string, password: string) => {
    try {
      const res = await fetch(`${getApiUrl()}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const body = await res.json().catch(() => ({}));

      if (res.status === 200 && body?.token) {
        const session: StoredSession = {
          token: body.token,
          user: body.user ?? { username, role: 'operator' },
          expiresAt: body.expires_at ?? Date.now() / 1000 + 86400,
        };
        await persistSession(session);
        applySession(session);
        return { ok: true };
      }
      if (res.status === 429) {
        const detail: string = body?.detail ?? '';
        const match = /en (\d+)s/.exec(detail);
        const retryAfter = match ? parseInt(match[1], 10) : 60;
        return { ok: false, error: detail || 'Demasiados intentos. Espera unos minutos.', retryAfter };
      }
      if (res.status === 401) {
        return { ok: false, error: body?.detail ?? 'Credenciales inválidas' };
      }
      return { ok: false, error: body?.detail ?? `Error del servidor (${res.status})` };
    } catch {
      return { ok: false, error: 'No se pudo conectar al servidor. Verifica la IP del backend o usa el modo demo.' };
    }
  }, [applySession]);

  const logout = useCallback(() => {
    const current = sessionRef.current;
    if (current) {
      fetch(`${getApiUrl()}/api/auth/logout`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${current.token}` },
      }).catch(() => {});
    }
    persistSession(null);
    sessionRef.current = null;
    setToken(null);
    setUser(null);
    setStatus('anonymous');
  }, []);

  const enterDemo = useCallback(() => {
    setToken(null);
    setUser(null);
    setStatus('demo');
  }, []);

  const value: AuthContextType = {
    status,
    token,
    user,
    isDemo: status === 'demo',
    login,
    logout,
    enterDemo,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
