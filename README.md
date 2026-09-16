# Travel planner

One-shot trip planner: describe a 2026 trip, get a grounded itinerary from the local flight/hotel catalog, then dummy-book ids. No real payments.

## Layout

```text
app/          Python package (API, planner, Gemini, catalog tools)
frontend/     Static UI
data/         Local catalogs only (see data/README.md; not on GitHub)
scripts/      Catalog generators / SQLite builders
tests/        pytest evals (no Gemini)
docs/         v1 spec (`docs/v1-implementation.md`)
infra/        Terraform (S3, ECR, EKS)
k8s/          Kubernetes manifests
```

## Local

1. Copy `.env.example` to `.env` and set `GEMINI_API_KEY`. Do not commit `.env`.
2. Generate the local catalog (not in git): see `data/README.md`.
3. Run the API:

```bash
uv run uvicorn app.api:app --reload
```

UI: http://127.0.0.1:8000/

CLI:

```bash
uv run python -m app.main "2 people, HYD to Munich on 2026-06-15, 3 nights, budget 4000"
```

Tests: `uv run pytest`

## Docker

The image does **not** include `catalog.sqlite` (~4 GB). Compose mounts `./data` read-only.

```bash
docker compose up --build
```

Then open http://127.0.0.1:8000/

## AWS (Terraform)

`infra/` provisions S3 (catalog file), ECR (image), and EKS (the worker **EC2** instances are the managed node group). See `infra/README.md`. Do not `terraform apply` unless you want AWS charges; `terraform destroy` when finished.

`k8s/` is the cluster side: copy sqlite from S3, run the API. See `k8s/README.md`.
