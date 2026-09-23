MAIN = paper
LATEX = pdflatex
LATEXFLAGS = -interaction=nonstopmode -halt-on-error -file-line-error

.PHONY: pdf metrics replay figures reproduce clean open

metrics:
	python3 scripts/aggregate_metrics.py

replay:
	python3 scripts/threshold_replay.py --csv data/benchmark_data.csv --out data/threshold_sensitivity.json

figures:
	python3 scripts/generate_figures.py

reproduce: metrics replay figures pdf

pdf: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex IEEEtran.cls sections/*.tex
	$(LATEX) $(LATEXFLAGS) $(MAIN).tex
	$(LATEX) $(LATEXFLAGS) $(MAIN).tex

clean:
	rm -f $(MAIN).{aux,log,out,toc,lof,lot,fls,fdb_latexmk,synctex.gz,bbl,blg}

open: pdf
	open $(MAIN).pdf
