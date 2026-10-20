set -e
export TODO_DB="$(mktemp -d)/todo.json"
python3 todo.py add "buy milk" >/dev/null
python3 todo.py add "write code" >/dev/null
python3 todo.py done 1
python3 todo.py list | grep -q "1. \[x\] buy milk"
python3 todo.py list | grep -q "2. \[ \] write code"
[ "$(python3 todo.py list --pending)" = "2. [ ] write code" ]
set +e
python3 todo.py done 99 2>/dev/null; [ $? -eq 1 ] || exit 1
set -e
unset TODO_DB
python3 -m unittest -q 2>/dev/null
