PY ?= python3
install:
	$(PY) -m pip install -r requirements-dev.txt
train:
	$(PY) -m backend.manage train
run:
	$(PY) run.py
test:
	$(PY) -m pytest
e2e:
	$(PY) tests/e2e_smoke.py
.PHONY: install train run test e2e
