# Frontend — AI Resume Analyzer dashboard

Next.js (App Router) static export, served from S3 through CloudFront (`infra/frontend.tf`).

- `/` — sign in / sign up (Cognito, SRP), new analysis form (job title, job description, PDF CV),
  history with status and ATS score.
- `/analysis/?id=<analysis id>` — polls `GET /analyses/{id}` every 3 s until DONE or FAILED,
  then shows the ATS score, matched / missing skills and prioritized suggestions.

Upload flow: `POST /analyses` → pre-signed S3 POST (`upload.url` + `upload.fields`) → the browser
posts the PDF as multipart form data straight to S3 → the S3 event starts the pipeline.

## Run locally
```bash
npm ci
cp config.example.json public/config.json   # fill in from `terraform output`
npm run dev                                 # http://localhost:3000 (allowed by the API CORS)
npm run typecheck && npm test               # tsc + node --test
npm run build                               # static export into out/
```

`public/config.json` is not committed; in AWS the `deploy-frontend` CI job writes it from the
stack outputs (`api_url`, `aws_region`, `cognito_user_pool_id`, `cognito_client_id`).
