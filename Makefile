.PHONY: setup pipeline manifests analyze test lint verify-data all clean
METROS := phoenix memphis los_angeles dallas denver atlanta chicago seattle miami

setup:
	uv sync

pipeline:      ## build all metros (Prefect resumes completed fetch steps from the 7-day result cache)
	uv run python run_pipeline.py --all

manifests:     ## (re)generate provenance manifests for existing final CSVs (offline)
	uv run python run_pipeline.py --generate-manifests

analyze:       ## run RQ1/2/3 for all metros
	uv run python run_analysis.py --all

test:
	uv run pytest -m "not network"

lint:
	uv run ruff check src/ tests/

verify-data:   ## offline checksum/schema drift check
	uv run python run_pipeline.py --verify

all: setup pipeline analyze

clean:
	rm -rf .prefect_cache/ .cache/ .coverage coverage.xml
