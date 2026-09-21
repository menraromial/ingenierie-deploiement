# Figures du cours : src/*.tex -> ../static/figures/*.svg (+ PDF pour l'impression)
#   make          toutes les figures
#   make <nom>    une seule figure (ex. make hyperviseurs)
#   make clean    supprime le dossier de build
SHELL := /bin/bash
export TEXINPUTS := ./lib:$(TEXINPUTS)
BUILD := build
OUT   := ../static/figures
NAMES := $(basename $(notdir $(wildcard src/*.tex)))
SVG   := $(addprefix $(OUT)/,$(addsuffix .svg,$(NAMES)))

.PRECIOUS: $(BUILD)/%.pdf
.PHONY: all clean $(NAMES)
all: $(SVG)
$(NAMES): %: $(OUT)/%.svg

$(BUILD)/%.pdf: src/%.tex lib/coursfig.sty | $(BUILD)
	@latexmk -lualatex -interaction=nonstopmode -halt-on-error \
	   -output-directory=$(BUILD) $< > $(BUILD)/$*.build.log 2>&1 \
	 || { echo "ÉCHEC $<"; tail -n 20 $(BUILD)/$*.build.log; exit 1; }

$(OUT)/%.svg: $(BUILD)/%.pdf | $(OUT)
	@pdftocairo -svg $< $@ && cp $< $(OUT)/$*.pdf && echo "SVG  $@"

$(BUILD) $(OUT):
	@mkdir -p $@
clean:
	@rm -rf $(BUILD)
