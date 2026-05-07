before = set(globals().keys())
from common_head import *
after = set(globals().keys())
new_vars = sorted(after - before - {"before", "after", "new_vars"})
print("New variables introduced by common_head:", new_vars)
