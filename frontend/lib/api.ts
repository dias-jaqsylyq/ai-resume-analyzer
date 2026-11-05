// Client for the user API (API Gateway HTTP API + Cognito JWT) and the pre-signed S3 upload.
import type { AnalysisDetail, HistoryPage, Status } from "./report.ts";

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
export const MAX_JOB_DESCRIPTION_CHARS = 10_000;
export const MAX_JOB_TITLE_CHARS = 200;

export type Upload = {
  method: "POST";
  url: string;
  fields: Record<string, string>;
  max_bytes: number;
  content_type: string;
  expires_in: number;
};

export type CreatedAnalysis = {
  analysis_id: string;
  status: Status;
  created_at: string;
  upload: Upload;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export type TokenProvider = () => Promise<string>;
type Fetch = typeof fetch;

/** Checks the file in the browser before anything is sent (S3 enforces the same limits). */
export function validateCv(file: { name: string; type: string; size: number }): string | null {
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) return "Please choose a PDF file.";
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) return "The PDF must be 5 MB or smaller.";
  return null;
}

export function validateJob(jobDescription: string, jobTitle: string): string | null {
  const jd = jobDescription.trim();
  if (!jd) return "Paste the job description.";
  if (jd.length > MAX_JOB_DESCRIPTION_CHARS) {
    return `The job description is longer than ${MAX_JOB_DESCRIPTION_CHARS.toLocaleString()} characters.`;
  }
  if (jobTitle.trim().length > MAX_JOB_TITLE_CHARS) {
    return `The job title is longer than ${MAX_JOB_TITLE_CHARS} characters.`;
  }
  return null;
}

/** multipart/form-data for the pre-signed POST: policy fields first, the file last (S3 rule). */
export function buildUploadForm(upload: Upload, file: Blob): FormData {
  const form = new FormData();
  for (const [key, value] of Object.entries(upload.fields)) form.append(key, value);
  form.append("file", file);
  return form;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly token: TokenProvider;
  private readonly fetchImpl: Fetch;

  constructor(baseUrl: string, token: TokenProvider, fetchImpl: Fetch = (...args) => fetch(...args)) {
    this.baseUrl = baseUrl;
    this.token = token;
    this.fetchImpl = fetchImpl;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${await this.token()}`);
    if (init.body) headers.set("Content-Type", "application/json");
    const res = await this.fetchImpl(new URL(path, this.baseUrl).toString(), { ...init, headers });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      const code = (body && typeof body.error === "string" && body.error) || `http_${res.status}`;
      const message =
        res.status === 401
          ? "Your session has expired. Please sign in again."
          : res.status === 429
            ? "Too many requests. Please wait a few seconds and try again."
            : (body && typeof body.message === "string" && body.message) || "Request failed.";
      throw new ApiError(res.status, code, message);
    }
    return body as T;
  }

  createAnalysis(jobDescription: string, jobTitle?: string): Promise<CreatedAnalysis> {
    const payload: Record<string, string> = { job_description: jobDescription.trim() };
    if (jobTitle?.trim()) payload.job_title = jobTitle.trim();
    return this.request("analyses", { method: "POST", body: JSON.stringify(payload) });
  }

  listAnalyses(limit = 20, cursor?: string | null): Promise<HistoryPage> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return this.request(`analyses?${params}`);
  }

  getAnalysis(analysisId: string): Promise<AnalysisDetail> {
    return this.request(`analyses/${encodeURIComponent(analysisId)}`);
  }

  /** Sends the PDF straight to S3; the S3 event starts the analysis pipeline. */
  async uploadCv(upload: Upload, file: Blob): Promise<void> {
    const res = await this.fetchImpl(upload.url, { method: "POST", body: buildUploadForm(upload, file) });
    if (!res.ok) {
      // S3 answers 403 with an XML body for an expired policy or a file outside the limits.
      throw new ApiError(res.status, "upload_failed", "The upload was rejected. Check the file and try again.");
    }
  }
}
