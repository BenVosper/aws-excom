#!/usr/bin/env bash

set -e
set -u
set -o pipefail

rm -rf dist
python3 -m build

# Requires TWINE_USERNAME and TWINE_PASSWORD envvars
python3 -m twine upload dist/*
