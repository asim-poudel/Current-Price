import type { ApiError, ApiResult, Evaluation, EvaluationSeries, Forecast, Health } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "";

async function get<T>(path: string): Promise<ApiResult<T>> {
  if (!API_BASE) {
    return {
      data: null,
      issue: { kind: "not_configured", message: "The backend API address is not configured." },
    };
  }
  try {
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (response.ok) return { data: await response.json(), issue: null };
    const body = await response.json().catch(() => null) as ApiError | null;
    return {
      data: null,
      issue: {
        kind: "response_error",
        status: response.status,
        code: body?.error?.code,
        message: body?.error?.message ?? "The backend could not complete the request.",
      },
    };
  } catch {
    return {
      data: null,
      issue: { kind: "unreachable", message: "The backend could not be reached." },
    };
  }
}

export async function getDashboardData() {
  const [health, forecast, evaluation, series] = await Promise.all([
    get<Health>("/api/health"),
    get<Forecast>("/api/forecast/current"),
    get<Evaluation>("/api/evaluation/latest"),
    get<EvaluationSeries>("/api/evaluation/latest/series"),
  ]);
  return { health, forecast, evaluation, series };
}
