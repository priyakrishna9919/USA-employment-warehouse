.PHONY: sample download load api test

sample:        ## generate synthetic data + build warehouse (works offline)
	python -m etl.sample_data --rows 8000
	python -m etl.load
	python -m etl.export

download:      ## download real DOL disclosure files (large!)
	python -m etl.download

load:          ## load whatever is in data/raw/lca into DuckDB
	python -m etl.load
	python -m etl.export

api:           ## start the REST API on :8000
	uvicorn api.main:app --reload

test:
	python -m pytest tests/ -q
dashboard:     ## serve the static dashboard locally on :8080
	python -m http.server 8080 -d docs
