set -e
# the fix commit's own tests (hidden) over the builder's work, then the whole suite
cp -r "$ASH_EVAL_DIR/hidden/." .
PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider tests --ignore=tests/property 2>&1 | tail -20
exit ${PIPESTATUS[0]}
