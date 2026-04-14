.DEFAULT_GOAL := help
PYTHON        := uv run

.PHONY: help install test fetch batch

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	    | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install all dependencies
	uv sync

test:  ## Run the test suite
	$(PYTHON) pytest -v

fetch:  ## Fetch a single ISBN — usage: make fetch ISBN=9786161842714
ifndef ISBN
	$(error ISBN is not set. Usage: make fetch ISBN=9786161842714)
endif
	$(PYTHON) thai-isbn fetch $(ISBN)

batch:  ## Fetch ISBNs from a file — usage: make batch FILE=isbn_list.txt
ifndef FILE
	$(error FILE is not set. Usage: make batch FILE=isbn_list.txt)
endif
	$(PYTHON) thai-isbn fetch --batch $(FILE)
