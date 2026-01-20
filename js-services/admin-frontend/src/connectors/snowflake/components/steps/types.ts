export interface CredentialsValidationState {
  isValid: boolean;
  error: string | null;
}

export const parseCredentialsJson = (
  json: string
): { clientId: string; clientSecret: string } | null => {
  if (!json.trim()) return null;

  try {
    const parsed = JSON.parse(json) as {
      OAUTH_CLIENT_ID?: string;
      OAUTH_CLIENT_SECRET?: string;
    };

    if (parsed.OAUTH_CLIENT_ID && parsed.OAUTH_CLIENT_SECRET) {
      return {
        clientId: parsed.OAUTH_CLIENT_ID,
        clientSecret: parsed.OAUTH_CLIENT_SECRET,
      };
    }
    return null;
  } catch {
    return null;
  }
};
