import math

def ordinal(n: int) -> str:
    return "%d%s" % (n,"tsnrhtdd"[(math.floor(n/10)%10!=1)*(n%10<4)*n%10::4])

def percent(x: float, digits=1):
    return f"{x:.{digits}f}%"
