# Usage: make install | make test | make lint | make all
#        make cpi | make retail | make gold | make reconcile
PYTHON ?= .venv/bin/python
BOOTSTRAP_PYTHON ?= /opt/anaconda3/bin/python
# macOS can hide the editable-install .pth under iCloud-synced Desktop, so set this explicitly.
export PYTHONPATH := $(CURDIR)

.PHONY: install lint format test cpi retail gold reconcile all

install:
	# .nosync keeps these out of iCloud, which offloads files and makes reads hang.
	mkdir -p data.nosync
	ln -sfn data.nosync data
	$(BOOTSTRAP_PYTHON) -m venv .venv.nosync
	ln -sfn .venv.nosync .venv
	$(PYTHON) -m pip install --quiet --upgrade pip
	$(PYTHON) -m pip install --quiet -r requirements.lock
	$(PYTHON) -m pip install --quiet --no-deps -e .

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) -m pytest -q

cpi:
	$(PYTHON) -m ingestion.sarb.cpi

retail:
	$(PYTHON) -m ingestion.stats_sa.retail_trade

gold:
	$(PYTHON) -m transform.build

reconcile:
	$(PYTHON) scripts/reconcile_august_2026.py

all: cpi retail gold
