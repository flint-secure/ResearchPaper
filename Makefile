.PHONY: metrics replay figures reproduce

metrics:
	python3 scripts/aggregate_metrics.py

replay:
	python3 scripts/threshold_replay.py --csv data/benchmark_data.csv --out data/threshold_sensitivity.json

figures:
	python3 scripts/generate_figures.py

reproduce: metrics replay figures
