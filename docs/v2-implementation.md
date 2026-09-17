# V2

V1 was one prompt → one itinerary. V2 adds conversation, per-leg/per-stay filters, a timeline tool, streaming, and `/metrics`.

## Confirm and edit

`POST /chat` and `POST /chat/stream` take `{ "prompt", "session_id"? }`.

1. First message extracts a spec and runs catalog tools. The reply asks you to **confirm** or change something.
2. `confirm` / `yes` / `looks good` locks the session.
3. Any other follow-up patches the spec (people, dates, city hotel filters, a leg time of day) and plans again.
4. **New trip** in the UI clears `session_id`.

Sessions live in process memory (fine for one replica).

## Per-city / per-leg spec

- `legs[]` may set `time_of_day` and `cabin` for that hop.
- `stays[]` may set `min_stars` and `amenities` for that city.
- Top-level `hotel` / `flight` remain defaults.

## Timeline tool

`check_timeline` validates chosen ids against check-in, checkout, and a 3-hour airport buffer. The agent should call it after `score_budget`.

## Streaming

`POST /chat/stream` is SSE (`data: {json}`). Events: `status`, `spec`, `tool`, `tool_result`, `text`, `error`, `done`.

## Metrics

`GET /metrics` (Prometheus). Live deploy still uses `infra/` Terraform + `k8s/` after you `terraform apply` and push ECR; this repo cannot create your AWS account for you.

## Evals

`tests/test_v2.py` covers confirm/edit sessions (mocked LLM), per-stay/per-leg overrides, and timeline checks. Existing planner tests still run against `catalog.sqlite`.
