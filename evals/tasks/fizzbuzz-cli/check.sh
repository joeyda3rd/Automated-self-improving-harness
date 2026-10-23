set -e
expected=$(printf '1\n2\nFizz\n4\nBuzz\nFizz\n7\n8\nFizz\nBuzz\n11\nFizz\n13\n14\nFizzBuzz')
[ "$(python3 fizzbuzz.py 15)" = "$expected" ]
[ "$(python3 fizzbuzz.py 1)" = "1" ]
set +e
python3 fizzbuzz.py abc >/dev/null 2>/tmp/ash-fb-err; code=$?
[ $code -eq 2 ] && [ -s /tmp/ash-fb-err ] || exit 1
python3 fizzbuzz.py 0 >/dev/null 2>&1; [ $? -eq 2 ] || exit 1
python3 fizzbuzz.py >/dev/null 2>&1; [ $? -eq 2 ] || exit 1
python3 -m unittest -q 2>/dev/null
