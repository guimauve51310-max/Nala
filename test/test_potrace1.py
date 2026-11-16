import numpy as np
from potrace import Bitmap

data = np.zeros((20, 20), dtype=np.uint32)
data[5:15, 5:15] = 1
bmp = Bitmap(data)
path = bmp.trace()

for curve in path:
    dp = curve.decomposition_points
    print("dp type:", type(dp))
    print("dp len:", len(dp) if hasattr(dp, '__len__') else "N/A")
    if hasattr(dp, '__len__') and len(dp) > 0:
        p0 = dp[0]
        print("dp[0] type:", type(p0))
        print("dp[0].x =", getattr(p0, 'x', 'N/A'), " dp[0].y =", getattr(p0, 'y', 'N/A'))
        print("dp full (5 premiers):", [(getattr(p, 'x', None), getattr(p, 'y', None)) for p in list(dp)[:5]])
    break