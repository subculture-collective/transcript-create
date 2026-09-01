# Dependencies

**Status:** shipped contract (2026-07-12).

Python production dependencies are split between `requirements-api.txt` and `requirements-worker.txt`, with shared pins in `constraints.txt`. Development-only tooling is in `requirements-dev.txt`. Frontend and browser dependencies are locked separately under `frontend/` and `e2e/`.

Python 3.11 and Node 20 are required. `make verify` runs pip-audit and npm audit. Stripe is not a code dependency: voluntary support redirects to a validated Stripe-hosted Payment Link, while billing remains disabled.
