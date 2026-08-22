#!/bin/bash
if [ -e "/run/current-system/sw/bin/nixos-version" ]; then
    if [ -n "${NIX_LD_LIBRARY_PATH:-}" ]; then
        export LD_LIBRARY_PATH="${NIX_LD_LIBRARY_PATH}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    fi
fi
export PYTHONPATH=$(pwd)
source .venv/bin/activate
python scratch/test_step.py
