// Runtime config: /config.json is written by the deploy job from Terraform outputs, so one
// build works for any stack and no ids are baked into the bundle or the repo.

export type AppConfig = {
  apiUrl: string;
  region: string;
  userPoolId: string;
  clientId: string;
};

const KEYS: (keyof AppConfig)[] = ["apiUrl", "region", "userPoolId", "clientId"];

export function parseConfig(raw: unknown): AppConfig {
  if (!raw || typeof raw !== "object") throw new Error("config.json is not an object");
  const obj = raw as Record<string, unknown>;
  for (const key of KEYS) {
    if (typeof obj[key] !== "string" || !(obj[key] as string).trim()) {
      throw new Error(`config.json is missing "${key}"`);
    }
  }
  const apiUrl = (obj.apiUrl as string).trim();
  if (!apiUrl.startsWith("https://") && !apiUrl.startsWith("http://localhost")) {
    throw new Error("config.json apiUrl must be https");
  }
  return {
    apiUrl: apiUrl.endsWith("/") ? apiUrl : `${apiUrl}/`,
    region: (obj.region as string).trim(),
    userPoolId: (obj.userPoolId as string).trim(),
    clientId: (obj.clientId as string).trim(),
  };
}

let cached: Promise<AppConfig> | null = null;

export function loadConfig(): Promise<AppConfig> {
  cached ??= fetch("/config.json", { cache: "no-store" })
    .then((res) => {
      if (!res.ok) throw new Error(`config.json: HTTP ${res.status}`);
      return res.json();
    })
    .then(parseConfig)
    .catch((err) => {
      cached = null;
      throw err;
    });
  return cached;
}
