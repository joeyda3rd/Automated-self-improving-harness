import sys
def fb(n):
    return ["FizzBuzz" if i%15==0 else "Fizz" if i%3==0 else "Buzz" if i%5==0 else str(i) for i in range(1,n+1)]
if __name__=="__main__":
    try:
        n=int(sys.argv[1]); assert n>0
    except Exception:
        print("usage: fizzbuzz.py N", file=sys.stderr); sys.exit(2)
    print("\n".join(fb(n)))
