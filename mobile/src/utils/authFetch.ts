let currentToken: string | null = null;

export const setAuthToken = (token: string | null): void => {
  currentToken = token;
};

export const getAuthToken = (): string | null => currentToken;

export const authFetch = (input: RequestInfo, init?: RequestInit): Promise<Response> => {
  const headers = new Headers(init?.headers);
  if (currentToken) headers.set('Authorization', `Bearer ${currentToken}`);
  return fetch(input, { ...init, headers });
};
