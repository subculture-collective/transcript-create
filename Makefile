
.PHONY: gen-ports
gen-ports:
	@echo "Generating .env with random free host ports..."
	@python3 scripts/gen_ports.py
	@echo "Wrote .env -- start services with: docker compose up -d"
