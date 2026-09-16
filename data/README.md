# Catalog data (not in git)

This folder is local-only. CSVs, `flights.csv.gz`, and `catalog.sqlite` are gitignored (~4 GB sqlite, large gzip).

From the repo root:

```bash
python scripts/generate_flights.py
python scripts/generate_hotels.py
python scripts/build_flights_db.py
python scripts/build_hotels_db.py
```

`airports.csv` is produced/used by those scripts. Docker Compose mounts this directory into the app container.
