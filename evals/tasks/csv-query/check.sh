set -e
d=$(mktemp -d)
cat > $d/p.csv <<'CSV'
id,name,dept,salary,bonus,city,code
1,Ann,eng,100,10,Oslo,10
2,Bob,eng,80,,Rome,9
3,"Cy, Jr.",ops,,5,Oslo,100
4,Dee,ops,90,0,,abc
5,O'Brien,eng,80,7.5,Rome,9
6,Eve,,70,,Oslo,
7,Fay,sales,90,2.25,Rome,10
CSV
cat > $d/n.csv <<'CSV'
x,y,k,e,v,w
0.1,1,9,,1.50,1e3
0.2,2,100,,007,20
-0.3,2,10,,2,3
CSV
printf 'a\n1.0000005\n' > $d/h1.csv
printf 'a\n-2.0000005\n-0.0000001\n0.0000006\n-1.0000015\n' > $d/h2.csv
here=$(pwd)
cd $d
PYTHONPATH="$here" timeout 50 python3 - <<'PY'
from csvq import run, QueryError

def eq(sql, *lines):
    want = "".join(l + "\n" for l in lines)
    got = run(sql)
    assert got == want, f"{sql}\n got: {got!r}\nwant: {want!r}"

# NULL semantics in WHERE
eq("SELECT name FROM p.csv WHERE bonus != 5", "name", "Ann", "Dee", "O'Brien", "Fay")
eq("SELECT name FROM p.csv WHERE NOT (salary > 85 AND city = 'Rome')",
   "name", "Ann", "Bob", '"Cy, Jr."', "O'Brien", "Eve")
eq("SELECT id FROM p.csv WHERE bonus > 6 OR city IS NULL", "id", "1", "4", "5")
eq("SELECT id FROM p.csv WHERE NOT NOT bonus IS NOT NULL AND id >= 3", "id", "3", "4", "5", "7")
eq("SELECT id FROM p.csv WHERE name < city", "id", "1", "2", "3", "5", "6", "7")
# precedence
eq("SELECT id FROM p.csv WHERE dept = 'ops' OR dept = 'eng' AND salary < 90", "id", "2", "3", "4", "5")
eq("SELECT id FROM p.csv WHERE NOT dept = 'eng' AND salary >= 90", "id", "4", "7")
eq("SELECT id FROM p.csv WHERE (dept = 'ops' OR dept = 'eng') AND NOT salary < 90", "id", "1", "4")
# literals, keywords, *
eq("select id, NAME from p.csv where name = 'O''Brien'".replace("NAME", "name"), "id,name", "5,O'Brien")
eq("select * from p.csv where id < 3 and 1 = 1",
   "id,name,dept,salary,bonus,city,code", "1,Ann,eng,100,10,Oslo,10", "2,Bob,eng,80,,Rome,9")
eq("SELECT id FROM p.csv WHERE salary <> 80 AND salary>-5 AND id<=4", "id", "1", "4")
# typing: code is a string column, k is numeric
eq("SELECT code FROM p.csv WHERE code > '5' ORDER BY code", "code", "9", "9", "abc")
eq("SELECT k FROM n.csv ORDER BY k", "k", "9", "10", "100")
eq("SELECT w FROM n.csv ORDER BY w", "w", "1e3", "20", "3")
eq("SELECT v FROM n.csv WHERE v >= 1.5 ORDER BY v DESC", "v", "007", "2", "1.50")
eq("SELECT MIN(v), MAX(v), MAX(w), SUM(v) FROM n.csv", "MIN(v),MAX(v),MAX(w),SUM(v)", "1.50,007,3,10.5")
# ORDER BY: NULL placement, multiple keys, stable ties in both directions, LIMIT
eq("SELECT id FROM p.csv ORDER BY salary DESC, id DESC", "id", "1", "7", "4", "5", "2", "6", "3")
eq("SELECT name, city FROM p.csv ORDER BY city DESC",
   "name,city", "Bob,Rome", "O'Brien,Rome", "Fay,Rome", "Ann,Oslo", '"Cy, Jr.",Oslo', "Eve,Oslo", "Dee,")
eq("SELECT id FROM p.csv ORDER BY bonus LIMIT 4", "id", "2", "6", "4", "7")
eq("SELECT name FROM p.csv ORDER BY code DESC LIMIT 3", "name", "Dee", "Bob", "O'Brien")
eq("SELECT id FROM p.csv ORDER BY dept, salary DESC", "id", "6", "1", "2", "5", "4", "3", "7")
eq("SELECT id FROM p.csv ORDER BY id LIMIT 0", "id")
# aggregates and grouping
eq("SELECT dept, COUNT(*), COUNT(bonus), SUM(bonus), AVG(salary), MIN(name), MAX(salary) FROM p.csv "
   "GROUP BY dept ORDER BY COUNT(*) DESC, dept",
   "dept,COUNT(*),COUNT(bonus),SUM(bonus),AVG(salary),MIN(name),MAX(salary)",
   "eng,3,2,17.5,86.666667,Ann,100", 'ops,2,2,5,90,"Cy, Jr.",90', ",1,0,,70,Eve,70", "sales,1,1,2.25,90,Fay,90")
eq("select dept from p.csv group by dept order by sum(salary) desc limit 2", "dept", "eng", "ops")
eq("SELECT city, dept, COUNT(*) FROM p.csv GROUP BY city, dept",
   "city,dept,COUNT(*)", "Oslo,eng,1", "Rome,eng,2", "Oslo,ops,1", ",ops,1", "Oslo,,1", "Rome,sales,1")
eq("SELECT COUNT(*) FROM p.csv GROUP BY city ORDER BY city DESC", "COUNT(*)", "3", "3", "1")
eq("SELECT COUNT(*), COUNT(name), SUM(salary), MIN(city) FROM p.csv WHERE salary > 1000",
   "COUNT(*),COUNT(name),SUM(salary),MIN(city)", "0,0,,")
eq("SELECT dept, COUNT(*) FROM p.csv WHERE salary > 1000 GROUP BY dept", "dept,COUNT(*)")
eq("select count ( * ), Max( salary ) from p.csv where city <> 'Oslo'", "COUNT(*),MAX(salary)", "3,90")
eq("SELECT city FROM p.csv WHERE id > 1 GROUP BY city", "city", "Rome", "Oslo", "\"\"")  # csv.writer quotes a lone empty field
# number formatting
eq("SELECT SUM(x), AVG(y), SUM(e), COUNT(e), AVG(x) FROM n.csv", "SUM(x),AVG(y),SUM(e),COUNT(e),AVG(x)", "0,1.666667,,0,0")
eq("SELECT SUM(a), AVG(a) FROM h1.csv", "SUM(a),AVG(a)", "1.000001,1.000001")
eq("SELECT SUM(a), MIN(a), AVG(a) FROM h2.csv WHERE a > -1", "SUM(a),MIN(a),AVG(a)", "0.000001,-0.0000001,0")
eq("SELECT SUM(a) FROM h2.csv WHERE a < 0.0000001 AND a > -1", "SUM(a)", "0")
eq("SELECT SUM(bonus), AVG(bonus) FROM p.csv", "SUM(bonus),AVG(bonus)", "24.75,4.95")
eq("SELECT SUM(a) FROM h2.csv WHERE a < -2", "SUM(a)", "-2.000001")
eq("SELECT SUM(a), AVG(a) FROM h2.csv WHERE a < -1", "SUM(a),AVG(a)", "-3.000002,-1.500001")

bad = [
    "SELECT nope FROM p.csv", "SELECT name FROM p.csv WHERE ID = 1",
    "SELECT name FROM p.csv WHERE salary = '80'", "SELECT name FROM p.csv WHERE code = 9",
    "SELECT name FROM p.csv WHERE salary > 1000 AND code = 9", "SELECT name FROM p.csv WHERE 'a' = 1",
    "SELECT SUM(code) FROM p.csv", "SELECT AVG(name) FROM p.csv WHERE id > 99",
    "SELECT name, COUNT(*) FROM p.csv", "SELECT name FROM p.csv GROUP BY dept",
    "SELECT * FROM p.csv GROUP BY dept", "SELECT dept FROM p.csv GROUP BY dept ORDER BY salary",
    "SELECT COUNT(*) FROM p.csv ORDER BY name", "SELECT name FROM p.csv WHERE name = 'abc",
    "SELECT name FROM p.csv WHERE", "SELECT name FROM p.csv LIMIT -1", "SELECT name FROM p.csv LIMIT 1.5",
    "SELECT name FROM p.csv LIMIT", "SELECT name FROM p.csv extra", "SELECT name FROM missing.csv",
    "SELECT FROM p.csv", "SELECT name FROM p.csv WHERE (salary > 1", "SELECT name FROM p.csv WHERE salary > 1)",
    "SELECT name FROM p.csv WHERE salary == 1", "SELECT name FROM p.csv WHERE salary = NULL",
    "SELECT COUNT(salary FROM p.csv", "SELECT SUM(*) FROM p.csv", "SELECT name FROM p.csv ORDER BY nope",
    "SELECT name FROM p.csv WHERE salary", "SELECT name name FROM p.csv", "SELECT name, FROM p.csv",
    "SELECT name FROM p.csv ORDER BY name LIMIT 2 WHERE id = 1", "SELECT name FROM p.csv GROUP BY",
    "SELECT name FROM", "SELECT name FROM p.csv WHERE NOT", "SELECT name FROM p.csv WHERE id IS 1",
]
for q in bad:
    try:
        r = run(q)
    except QueryError:
        continue
    except Exception as e:
        raise AssertionError(f"{q!r} raised {type(e).__name__}, not QueryError")
    raise AssertionError(f"{q!r} should raise QueryError, got {r!r}")
PY
cd "$here"
python3 -m unittest -q 2>/dev/null
