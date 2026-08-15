# ISCPS Project: Securing Multimodal Perception for a ROS 2 VLM-Based Embodied Agent

SHELL := /bin/bash
ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
PY ?= $(if $(wildcard $(ROOT)/.venv/bin/python3),$(ROOT)/.venv/bin/python3,python3)
FALSE_DISTANCE ?= 6.0
REPETITIONS ?= 3
GROUPID ?=

export ISCPS_LAB_ROOT := $(ROOT)

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show the command surface
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | sort | awk 'BEGIN {FS = ":.*?## "} {printf "  %-20s %s\n", $$1, $$2}'

.PHONY: doctor
doctor: ## Check the submodule, ROS/SST tools, and required live VLM access
	@$(PY) $(ROOT)/scripts/doctor.py

.PHONY: submodules
submodules: ## Initialize the pinned IoTAuth Git submodule
	@git -C $(ROOT) submodule update --init third_party/iotauth

.PHONY: setup
setup: ## Create .venv and install project dependencies and IoTAuth from the submodule
	@$(ROOT)/scripts/setup.sh

.PHONY: build
build: ## Build the ROS 2 Jazzy workspace
	@$(ROOT)/scripts/build.sh

.PHONY: build-auth
build-auth: ## Build Auth from third_party/iotauth/auth
	@$(ROOT)/sst/scripts/build_auth.sh

.PHONY: generate
generate: ## Generate all SST state under runtime/ (never in the submodule)
	@$(ROOT)/sst/scripts/generate_runtime.sh

.PHONY: test-offline
test-offline: ## Run model-free unit tests; these cannot satisfy grading
	@$(PY) -m pytest -q -m "not ros_integration and not sst_integration and not live_vlm"

.PHONY: test
test: test-offline ## Alias for test-offline

.PHONY: test-ros
test-ros: ## Run ROS-marked integration tests
	@$(PY) -m pytest -q -m ros_integration

.PHONY: test-sst
test-sst: ## Run SST-marked integration tests
	@$(PY) -m pytest -q -m sst_integration

.PHONY: test-live-vlm
test-live-vlm: ## Run live model integration tests
	@$(PY) -m pytest -q -m live_vlm

.PHONY: vlm-check
vlm-check: ## Check the server, model, vision, image, and structured response
	@$(PY) $(ROOT)/scripts/vlm_check.py

.PHONY: model-setup
model-setup: ## One-time explicit qwen2.5vl:3b download on a compute node
	@$(ROOT)/scripts/model_setup.sh

.PHONY: baseline
baseline: ## Live VLM with legitimate ROS inputs (expect STOP)
	@$(ROOT)/scripts/run_scenario.sh baseline

.PHONY: attack
attack: ## Live VLM with deterministic malicious distance replacement
	@FALSE_DISTANCE=$(FALSE_DISTANCE) $(ROOT)/scripts/run_scenario.sh attack \
	  --false-distance $(FALSE_DISTANCE)

.PHONY: attack-sweep
attack-sweep: ## Repeat live VLM attack trials over several false distances
	@REPETITIONS=$(REPETITIONS) $(ROOT)/scripts/attack_sweep.sh

.PHONY: secure
secure: ## Live VLM with two authenticated SST inputs (expect STOP)
	@$(ROOT)/scripts/run_scenario.sh secure

.PHONY: secure-attack
secure-attack: ## Reject unregistered distance source; do not pass it to the VLM
	@$(ROOT)/scripts/run_scenario.sh secure-attack

.PHONY: grad-vision-attack
grad-vision-attack: ## CSE 598: replace the red camera scene with green over ROS
	@$(ROOT)/scripts/run_scenario.sh grad-vision-attack

.PHONY: grad-vision-baseline
grad-vision-baseline: ## CSE 598: legitimate red camera control (expect STOP)
	@$(ROOT)/scripts/run_scenario.sh grad-vision-baseline

.PHONY: grad-vision-secure
grad-vision-secure: ## CSE 598: reject the unregistered camera over SST
	@$(ROOT)/scripts/run_scenario.sh grad-vision-secure

.PHONY: evaluate
evaluate: ## Evaluate the most recent completed experiment
	@$(PY) $(ROOT)/scripts/evaluate_run.py

.PHONY: auth-start
auth-start: ## Start Auth from runtime state
	@$(ROOT)/sst/scripts/start_auth.sh

.PHONY: auth-stop
auth-stop: ## Stop only the Auth process recorded by this project
	@$(ROOT)/sst/scripts/start_auth.sh --stop

.PHONY: submission
submission: ## Build the group ZIP; pass GROUPID=<groupid>
	@test -n "$(GROUPID)" || { echo "usage: make submission GROUPID=<groupid>" >&2; exit 2; }
	@$(PY) $(ROOT)/scripts/make_submission.py --groupid $(GROUPID)

.PHONY: lint
lint: ## Run ruff
	@$(PY) -m ruff check $(ROOT)

.PHONY: clean
clean: ## Remove build output, runtime secrets/state, results, and caches
	@$(ROOT)/scripts/clean.sh
