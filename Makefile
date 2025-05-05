
IN_VENV=. venv/bin/activate

# create venv
venv:
	python3 -m venv venv
	$(IN_VENV) ; pip install -U pip setuptools wheel

# install dependencies
.PHONY: deps
deps: venv/deps
venv/deps: venv requirements.txt requirements-dev.txt
	$(IN_VENV) ; pip install -Ur requirements.txt
	$(IN_VENV) ; pip install -Ur requirements-dev.txt
	@touch $(@)


# install typical checker script dependencies
deps-script: venv/deps venv/deps-script
venv/deps-script: venv gamelib/checker-default-requirements.txt
	$(IN_VENV) ; pip install -Ur gamelib/checker-default-requirements.txt
	@touch $(@)


# check project integrity
check: check-mypy
check-mypy: deps
	#TODO add --disallow-untyped-defs at some point
	$(IN_VENV) ; mypy --config-file mypy.ini --no-incremental checker_runner controlserver gamelib saarctf_commons scripts tests vpn vpnboard wireguard-sync/wireguard_sync


# run all the unittests
.PHONY: test
test: deps deps-script
	$(IN_VENV) ; python3 -m unittest tests/test_*.py


# cleanup everything including venv
.PHONY: clean
clean:
	rm -rf venv
	rm -rf .mypy_cache
	find . -ignore_readdir_race -type d -name __pycache__ -exec rm -rf {} \; 2>/dev/null || true
