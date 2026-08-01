#!/usr/bin/env bash
# Explicit one-time model download; graded runs never call this script.

set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
iscps_refuse_login_node
need_cmd ollama
MODEL="${VLM_MODEL:-qwen2.5vl:3b}"
log_step "One-time Ollama model setup: ${MODEL}"
ollama pull "${MODEL}"
