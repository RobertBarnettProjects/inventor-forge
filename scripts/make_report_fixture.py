"""Strip images and personal names from an Inventor stress report so it can be a test fixture.

    python scripts/make_report_fixture.py <report.html> tests/fixtures/<name>.html
"""
import os
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
with open(src, encoding="utf-8", errors="replace") as f:
    t = f.read()
t = re.sub(r"<img[^>]*>", "", t, flags=re.I)
t = re.sub(r"data:image/[^\"')]+", "", t)
t = re.sub(r"<script.*?</script>", "", t, flags=re.S | re.I)
user = os.path.basename(os.path.expanduser("~"))
t = t.replace(os.path.expanduser("~"), r"C:\Users\user").replace(user, "user")
os.makedirs(os.path.dirname(dst), exist_ok=True)
with open(dst, "w", encoding="utf-8") as f:
    f.write(t)
print(dst, len(t), "bytes")
