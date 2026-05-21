# bike-design-composite — web app

Password-protected web app: upload a Scarab paint-spec PDF, get back photoreal composites of the design on the Letras bike.

## Architecture

```
PDF upload → pypdfium2 render → crop side-view → Gemini 3 Pro Image (Vertex) → result page
```

- **Auth**: single shared password (env var `APP_PASSWORD`), signed session cookie.
- **Stack**: FastAPI + Jinja templates (no JS framework).
- **Hosting**: Cloud Run. Vertex AI auth via the service account attached to the Cloud Run service — no key files needed.

## Files

- `app.py` — FastAPI routes (login, index, generate, healthz).
- `extract.py` — PDF → cropped PNG of the side-view illustration.
- `composite.py` — Vertex AI call + bundled bike base photos.
- `templates/` — login, index, result.
- `static/bikes/` — bundled base photos (`studio.jpg`, `alley.jpg`).

## Local dev

```bash
cd web
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# ADC for Vertex
gcloud auth application-default login

export APP_PASSWORD='pick-something'
export SESSION_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
export GCP_PROJECT=time-279118

uvicorn app:app --reload --port 8080
```

Open <http://localhost:8080>. (Cookies are set with `Secure`, so local HTTP will only work if you change `secure=True` to `False` in `app.py`, or run with TLS, or use `127.0.0.1` via a proxy. Easiest: change `secure=True` temporarily for local dev.)

## Deploy to Cloud Run

```bash
# One-time: pick a region and create a service account with Vertex access
gcloud iam service-accounts create bike-design-runner --project time-279118
gcloud projects add-iam-policy-binding time-279118 \
  --member=serviceAccount:bike-design-runner@time-279118.iam.gserviceaccount.com \
  --role=roles/aiplatform.user

# Store the password as a Secret Manager secret
gcloud secrets create app-password --replication-policy=automatic --project time-279118
printf 'your-strong-password' | gcloud secrets versions add app-password --data-file=- --project time-279118

gcloud secrets create session-secret --replication-policy=automatic --project time-279118
python3 -c 'import secrets;print(secrets.token_urlsafe(32))' \
  | gcloud secrets versions add session-secret --data-file=- --project time-279118

# Deploy (builds via Cloud Build, no Dockerfile changes needed)
gcloud run deploy bike-design \
  --source=. \
  --region=us-central1 \
  --project=time-279118 \
  --service-account=bike-design-runner@time-279118.iam.gserviceaccount.com \
  --set-env-vars=GCP_PROJECT=time-279118,GCP_LOCATION=global \
  --set-secrets=APP_PASSWORD=app-password:latest,SESSION_SECRET=session-secret:latest \
  --allow-unauthenticated \
  --memory=1Gi \
  --timeout=300 \
  --concurrency=4
```

`--allow-unauthenticated` is fine because access is gated by the password. Bump `--timeout` if you ever composite onto many bases at once.

## Cost

~$0.15 per output image. Generating both studio + alley = ~$0.30 per upload.
