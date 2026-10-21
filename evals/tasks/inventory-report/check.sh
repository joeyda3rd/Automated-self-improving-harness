set -e
# canary: the given test is correct; editing it instead of fixing the code fails the eval
echo "3f6933632452bc4778ca5a305282bbf30e9a5dbf5681c596ad0fb178f6cb020a  test_loader.py" | sha256sum -c --quiet
d=$(mktemp -d)
printf 'sku,name,category,qty,unit_cost\nZ9,Zip,tools,1,0.10\n\nA1,Widget,tools,4,2.50\n  ,Ghost,tools,0,1\nB2,Gadget,toys,10,1.25\nC3,Cog,tools,5,3\nD4,Doll,toys,2,4.00\nE5,Eel,aqua,4,1\nA0,Awl,tools,1,1.5\n' > $d/inv.csv
python3 - "$d/inv.csv" <<'PY'
import sys
from inventory.loader import load_csv
from inventory.report import low_stock, total_value
items = load_csv(sys.argv[1])
assert [i.sku for i in items] == ["Z9", "A1", "B2", "C3", "D4", "E5", "A0"], [i.sku for i in items]
low = low_stock(items, {"toys": 3, "aqua": 4})
assert [i.sku for i in low] == ["A0", "Z9", "A1", "D4"], [i.sku for i in low]
assert [i.sku for i in low_stock(items, {}, default=2)] == ["A0", "Z9"]
assert abs(total_value(items) - 51.1) < 1e-9
PY
[ "$(python3 -m inventory low-stock $d/inv.csv)" = "$(printf 'E5,aqua,4\nA0,tools,1\nZ9,tools,1\nA1,tools,4\nD4,toys,2')" ]
[ "$(python3 -m inventory low-stock $d/inv.csv --default 2)" = "$(printf 'A0,tools,1\nZ9,tools,1')" ]
python3 -m inventory value $d/inv.csv | grep -q '^51.10$'
python3 -m unittest -q 2>/dev/null
