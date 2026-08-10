import type { AnalysisCreateResponse, AnalysisStatusResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data.detail === "string") {
      return data.detail;
    }
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object" && "msg" in item) {
            return String((item as { msg: unknown }).msg);
          }
          return JSON.stringify(item);
        })
        .join("; ");
    }
  } catch {
    // ignore JSON parse errors
  }
  return `Ошибка запроса (${response.status})`;
}

export async function createAnalysis(url: string): Promise<AnalysisCreateResponse> {
  const response = await fetch(`${API_BASE}/api/analyses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as AnalysisCreateResponse;
}

export async function getAnalysis(id: string): Promise<AnalysisStatusResponse> {
  const response = await fetch(`${API_BASE}/api/analyses/${encodeURIComponent(id)}`);
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as AnalysisStatusResponse;
}
