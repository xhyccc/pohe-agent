.PHONY: test scan match plan

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

scan:
	PYTHONPATH=src python3 -m pohe_agent scan examples/mini_harness

match:
	PYTHONPATH=src python3 -m pohe_agent match examples/mini_harness --pattern P01,P09

plan:
	PYTHONPATH=src python3 -m pohe_agent scan examples/mini_harness --json /tmp/pohe-findings.json
	PYTHONPATH=src python3 -m pohe_agent plan examples/mini_harness --findings /tmp/pohe-findings.json --goal "harden the example harness" -o /tmp/pohe-evolution.md
