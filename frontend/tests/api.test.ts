import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiClient, ApiError, buildUploadForm, validateCv, validateJob, type Upload } from "../lib/api.ts";

const upload: Upload = {
  method: "POST",
  url: "https://bucket.s3.us-east-1.amazonaws.com/",
  fields: { key: "uploads/sub/01ID.pdf", "Content-Type": "application/pdf", policy: "p", "x-amz-signature": "s" },
  max_bytes: 5 * 1024 * 1024,
  content_type: "application/pdf",
  expires_in: 300,
};

type Call = { url: string; init: RequestInit };

function fakeFetch(status: number, body: unknown, calls: Call[]): typeof fetch {
  return (async (url: string | URL | Request, init: RequestInit = {}) => {
    calls.push({ url: String(url), init });
    return new Response(body === undefined ? null : JSON.stringify(body), { status });
  }) as typeof fetch;
}

test("validateCv accepts a PDF up to 5 MiB only", () => {
  assert.equal(validateCv({ name: "cv.pdf", type: "application/pdf", size: 1000 }), null);
  assert.equal(validateCv({ name: "CV.PDF", type: "", size: 1000 }), null);
  assert.match(validateCv({ name: "cv.docx", type: "application/msword", size: 1000 })!, /PDF/);
  assert.match(validateCv({ name: "cv.pdf", type: "application/pdf", size: 0 })!, /empty/);
  assert.match(validateCv({ name: "cv.pdf", type: "application/pdf", size: 5 * 1024 * 1024 + 1 })!, /5 MB/);
});

test("validateJob mirrors the API limits", () => {
  assert.equal(validateJob("Python, AWS", ""), null);
  assert.match(validateJob("   ", "")!, /job description/);
  assert.match(validateJob("x".repeat(10_001), "")!, /longer/);
  assert.match(validateJob("ok", "t".repeat(201))!, /title/);
});

test("upload form puts the policy fields first and the file last", () => {
  const form = buildUploadForm(upload, new Blob(["%PDF-1.4"], { type: "application/pdf" }));
  const keys = [...form.keys()];
  assert.deepEqual(keys, ["key", "Content-Type", "policy", "x-amz-signature", "file"]);
  assert.equal(form.get("key"), "uploads/sub/01ID.pdf");
});

test("createAnalysis sends a bearer token and a trimmed JSON body", async () => {
  const calls: Call[] = [];
  const api = new ApiClient("https://api.example.com/", async () => "tok", fakeFetch(201, { analysis_id: "01ID" }, calls));
  await api.createAnalysis("  JD text  ", "  ");
  assert.equal(calls[0].url, "https://api.example.com/analyses");
  assert.equal(calls[0].init.method, "POST");
  const headers = new Headers(calls[0].init.headers);
  assert.equal(headers.get("authorization"), "Bearer tok");
  assert.equal(headers.get("content-type"), "application/json");
  assert.deepEqual(JSON.parse(calls[0].init.body as string), { job_description: "JD text" });
});

test("listAnalyses passes limit and cursor", async () => {
  const calls: Call[] = [];
  const api = new ApiClient("https://api.example.com/", async () => "tok", fakeFetch(200, { items: [], next_cursor: null }, calls));
  await api.listAnalyses(10, "01CURSOR");
  assert.equal(calls[0].url, "https://api.example.com/analyses?limit=10&cursor=01CURSOR");
});

test("API errors keep the code; 401 and 429 get friendly messages", async () => {
  const api = (status: number, body: unknown) =>
    new ApiClient("https://api.example.com/", async () => "tok", fakeFetch(status, body, []));
  await assert.rejects(api(404, { error: "not_found", message: "analysis not found" }).getAnalysis("x"), (e: unknown) => {
    assert.ok(e instanceof ApiError);
    assert.equal(e.status, 404);
    assert.equal(e.code, "not_found");
    return true;
  });
  await assert.rejects(api(401, { message: "Unauthorized" }).getAnalysis("x"), /sign in again/);
  await assert.rejects(api(429, { message: "Too Many Requests" }).listAnalyses(), /Too many requests/);
});

test("uploadCv posts multipart form to S3 without the API token", async () => {
  const calls: Call[] = [];
  const api = new ApiClient("https://api.example.com/", async () => "tok", fakeFetch(204, undefined, calls));
  await api.uploadCv(upload, new Blob(["%PDF"]));
  assert.equal(calls[0].url, upload.url);
  assert.ok(calls[0].init.body instanceof FormData);
  assert.equal(calls[0].init.headers, undefined, "no Authorization header goes to S3");

  const failing = new ApiClient("https://api.example.com/", async () => "tok", fakeFetch(403, undefined, []));
  await assert.rejects(failing.uploadCv(upload, new Blob(["%PDF"])), /rejected/);
});
