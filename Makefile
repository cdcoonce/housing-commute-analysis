.PHONY: setup pipeline panel manifests analyze test lint verify-data all clean
METROS := phoenix memphis los_angeles dallas denver atlanta chicago seattle miami

setup:
	uv sync

pipeline:      ## build all metros (Prefect resumes completed fetch steps from the 7-day result cache)
	uv run python run_pipeline.py --all

panel:         ## build RQ4 panel data products for all metros (shares the fetch cache with pipeline)
	uv run python run_pipeline.py --panel --all

manifests:     ## (re)generate provenance manifests for existing final CSVs (offline)
	uv run python run_pipeline.py --generate-manifests

analyze:       ## run RQ1-RQ4 for all metros (RQ4 runs where panel products exist)
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
