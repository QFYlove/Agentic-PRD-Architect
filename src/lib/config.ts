export const DEFAULT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";

export function resolvePublicApiBaseUrl(
  configuredValue: string | undefined = import.meta.env.PUBLIC_API_BASE_URL,
): string {
  const candidate = configuredValue?.trim() || DEFAULT_PUBLIC_API_BASE_URL;
  let parsed: URL;

  try {
    parsed = new URL(candidate);
  } catch {
    throw new TypeError("PUBLIC_API_BASE_URL must be an absolute HTTP(S) URL.");
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new TypeError("PUBLIC_API_BASE_URL must use HTTP or HTTPS.");
  }

  return parsed.toString().replace(/\/$/, "");
}
