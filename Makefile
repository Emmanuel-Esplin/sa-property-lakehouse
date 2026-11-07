# Usage: make install | make test | make lint | make all
#        make cpi | make retail | make gold | make reconcile
#        make tf-check | make tf-plan | make tf-apply | make tf-destroy
#        make glue-run | make dbt-athena | make cloud-check
PYTHON ?= .venv/bin/python
BOOTSTRAP_PYTHON ?= /opt/anaconda3/bin/python
# macOS can hide the editable-install .pth under iCloud-synced Desktop, so set this explicitly.
export PYTHONPATH := $(CURDIR)
# Spark 3.5 needs Java 8, 11 or 17, and this Mac's default is newer. CI sets its own JAVA_HOME.
JAVA_11 := $(shell /usr/libexec/java_home -v 11 2>/dev/null)
ifneq ($(JAVA_11),)
export JAVA_HOME := $(JAVA_11)
endif

# Provider binaries go in a .nosync folder, because iCloud offloading makes them hang.
export TF_DATA_DIR := .terraform.nosync
TF_DEV = terraform -chdir=infra/envs/dev

.PHONY: install lint format test cpi retail gold reconcile all \
	tf-check tf-plan tf-apply tf-destroy glue-run dbt-athena cloud-check

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
	$(PYTHON) -m transform.run

reconcile:
	$(PYTHON) scripts/reconcile_august_2026.py

all: cpi retail gold

# No AWS credentials needed: formatting, validation and module tests with a mocked provider.
tf-check:
	terraform fmt -check -recursive infra
	$(TF_DEV) init -input=false -upgrade=false >/dev/null
	$(TF_DEV) validate
	$(TF_DEV) test
	for m in budget s3_lake glue_job; do \
		terraform -chdir=infra/modules/$$m init -input=false >/dev/null && \
		terraform -chdir=infra/modules/$$m test || exit 1; \
	done

tf-plan:
	$(TF_DEV) init -input=false >/dev/null
	$(TF_DEV) plan -out=tfplan.nosync

tf-apply:
	$(TF_DEV) apply tfplan.nosync

tf-destroy:
	$(TF_DEV) destroy

LAKE_BUCKET = $$(terraform -chdir=infra/envs/dev output -raw lake_bucket)

# Spark on Glue: bronze to silver. Costs a few cents.
glue-run:
	bash scripts/run_glue_job.sh sa-property-lakehouse-bronze-to-silver

# dbt on Athena: silver to gold, with every data test. Costs under a cent.
dbt-athena:
	LAKE_BUCKET=$(LAKE_BUCKET) $(PYTHON) -m transform.run --target athena

# Checks the marts from the last `make dbt-athena` against the local marts and Stats SA's
# published figures.
cloud-check:
	aws s3 rm --recursive --quiet s3://$(LAKE_BUCKET)/exports/dbt/
	LAKE_BUCKET=$(LAKE_BUCKET) $(PYTHON) -m transform.run --target athena --export
	aws s3 sync --delete --only-show-errors s3://$(LAKE_BUCKET)/exports/dbt/ data/cloud_gold/
	$(PYTHON) scripts/compare_gold.py data/cloud_gold
	$(PYTHON) scripts/reconcile_august_2026.py data/cloud_gold
