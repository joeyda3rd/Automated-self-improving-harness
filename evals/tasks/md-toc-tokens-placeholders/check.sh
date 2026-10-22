set -e
# the fix commit's own tests (hidden) over the builder's work, then the whole suite
cp -r "$ASH_EVAL_DIR/hidden/." .
python3 run_tests.py 2>&1 | tail -20
exit ${PIPESTATUS[0]}
