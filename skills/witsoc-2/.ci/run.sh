#!/usr/bin/env bash
# Continuous check for witsoc-2.
#
# Runs the whole suite the way something that is not the author would: from a
# clean checkout, with nothing in the environment that was not declared. Every
# number this skill reports about itself was, until this existed, produced by
# the same process that wrote the code being measured.
#
# Toolchain-dependent checks report NOT_RUN without a backend, and NOT_RUN is
# counted and printed — never folded into a pass.
#
# Usage:  .ci/run.sh [--with-backend]
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

if [[ "${1:-}" == "--with-backend" ]]; then
  : "${WITSOC2_LEAN_PROJECT:?set WITSOC2_LEAN_PROJECT to a Lean project}"
  export WITSOC2_LEAN_PROJECT
  [[ -n "${WITSOC2_MATHS_CORPUS:-}" ]] && export WITSOC2_MATHS_CORPUS
fi

failed=0
for suite in --frame "--pack maths" "--pack bio" "--pack archival"; do
  echo "=== $suite ==="
  # shellcheck disable=SC2086
  bash scripts/check.sh $suite || failed=1
done

echo
if (( failed )); then
  echo "CI: FAIL — see the suite output above. A failure here is a finding about"
  echo "    the skill, not a broken test."
  exit 1
fi
echo "CI: PASS"
