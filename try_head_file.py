before = set(globals().keys())
from python_common_head import *
after = set(globals().keys())
new_vars = sorted(after - before - {"before", "after", "new_vars"})
print("New variables introduced by python_common_head:", new_vars)
