# test_potrace.py — test temporaire, à supprimer après
import numpy as np
from potrace import Bitmap

# Un petit carré 20x20 : 1 = noir (à vectoriser), 0 = blanc
data = np.zeros((20, 20), dtype=np.uint32)
data[5:15, 5:15] = 1

bmp = Bitmap(data)
path = bmp.trace()

print("type path:", type(path))
print("dir(path):", [a for a in dir(path) if not a.startswith("_")])

for i, curve in enumerate(path):
    print(f"\ncurve {i}: type={type(curve)}")
    print(f"  attrs: {[a for a in dir(curve) if not a.startswith('_')]}")
    print(f"  start_point={curve.start_point}")
    for j, seg in enumerate(curve):
        print(f"    seg {j}: type={type(seg)}")
        print(f"      attrs: {[a for a in dir(seg) if not a.startswith('_')]}")
        for attr in ("c1", "c2", "end_point"):
            if hasattr(seg, attr):
                print(f"      {attr}={getattr(seg, attr)}")
    break  # on inspecte juste la première courbe