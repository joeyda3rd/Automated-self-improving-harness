import os
import tempfile
import unittest

from inventory.loader import load_csv
from inventory.report import total_value

CSV = """sku,name,category,qty,unit_cost
A1,Widget,tools,4,2.50
B2,Gadget,toys,10,1.25
"""


class LoaderTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as fh:
            fh.write(CSV)

    def tearDown(self):
        os.remove(self.path)

    def test_loads_decimal_costs(self):
        items = load_csv(self.path)
        self.assertEqual([i.sku for i in items], ["A1", "B2"])
        self.assertEqual(items[0].unit_cost, 2.5)

    def test_total_value(self):
        self.assertEqual(total_value(load_csv(self.path)), 22.5)


if __name__ == "__main__":
    unittest.main()
