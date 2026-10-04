.PHONY: gen-ports openapi openapi-check verify verify-services-down verify-services-up

PYTHON_BIN ?= python3

verify:
	@./scripts/verify.sh

openapi:
	@$(PYTHON_BIN) scripts/generate_openapi.py docs/api/openapi.json
	@echo "Wrote docs/api/openapi.json"

openapi-check:
	@PYTHON_BIN="$(PYTHON_BIN)" ./scripts/check_api_contracts.sh

verify-services-up:
	@docker compose -p hasanara-test -f docker-compose.test.yml up -d --wait

verify-services-down:
	@docker compose -p hasanara-test -f docker-compose.test.yml down --volumes --remove-orphans

gen-ports:
	@echo "Generating .env with random free host ports..."
	@python3 scripts/gen_ports.py
	@echo "Wrote .env -- start services with: docker compose up -d"
