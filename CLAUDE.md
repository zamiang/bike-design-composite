# Repo notes for Claude

Read this before reviewing or proposing changes. It's the stuff that isn't in the code.

## What this is

A small password-gated FastAPI app that takes a Scarab paint-spec PDF, extracts the frame illustration, and uses Vertex AI's `gemini-3-pro-image-preview` to composite the design onto real bike photos. Lives in `web/`. Deploys to Cloud Run via Terraform in `infra/`, rolled by `.github/workflows/deploy.yml` on push to `main`.

`work/` holds one-off offline scripts from the original single-shot pipeline. Lint applies; design polish and architectural review don't, those are not production code.

## Stack reminders that trip up generic review

- **FastAPI, not Flask.** Don't suggest `url_for()`, `flask.request`, blueprints, or Jinja patterns that assume Flask globals. `File(...)`, `Form(...)`, `Depends(...)` as argument defaults are correct here, `B008` is intentionally ignored in `pyproject.toml`.
- **Jinja templates linted by djlint.** Several rules are intentionally ignored, see the comments under `[tool.djlint]` in `pyproject.toml`. Don't reopen them: `J018` (Flask-only), `H006` (data: URIs have no known dimensions), `H021` (one-off inline styles allowed), `H023` (`&rsquo;` / `&hellip;` are intentional typography), `H030`/`H031` (private app, no SEO meta), `T003` (endblock naming is stylistic).
- **Cloud Run `timeout = "900s"` is deliberate.** A composite takes 30–60s per base; with multiple bases per request, the default 60s would 504 immediately. Don't suggest lowering it.
- **`max_instance_request_concurrency = 4` is deliberate.** Image generation is CPU-heavy; higher concurrency starves the instance.
- **Cloud Run IAM is open to `allUsers` on purpose.** The app does its own password gate; adding IAM-level auth on top would block the `/login` page itself.

## Secrets and auth

- `APP_PASSWORD` and `SESSION_SECRET` live in Secret Manager. Never inline them in code, templates, workflows, or Terraform variables. Terraform manages the secret *resources*; values are seeded out-of-band, see `infra/README.md`.
- Vertex AI access in production comes from the attached Cloud Run service account (`paint-preview-runtime`). No key files anywhere. Don't suggest adding `GOOGLE_APPLICATION_CREDENTIALS` or service-account JSON to the container.
- GitHub Actions auths to GCP via Workload Identity Federation. Don't suggest API-key auth as an alternative; we deliberately don't carry long-lived GCP keys.

## Style

- **No em dashes in user-facing copy.** The web templates use commas, colons, parens. Don't add `—` in `web/templates/*.html`. Inside code comments and this file is fine.
- Templates lean editorial (Fraunces italic for display, Inter for UI, restrained terracotta accent). Don't reintroduce card panels with rounded corners and side-stripe accent borders, that style was deliberately removed.

## Review priorities, in order

1. **Security** at GCP/IAM boundaries: SA scope creep, overly broad role bindings, WIF attribute conditions, anything that widens the blast radius beyond this repo.
2. **Correctness** of the Cloud Run config and the Vertex client setup.
3. **Python**: real bugs, dropped exceptions, resource leaks.
4. **Templates**: actual structural problems (Jinja escaping, accessibility, form semantics). Skip stylistic nits already covered by djlint or the ignores list.
5. **Don't comment on `work/`** unless something is genuinely broken.

If feedback is preferential rather than correctness-driven, prefix it with `(nit)` so it's easy to triage.
