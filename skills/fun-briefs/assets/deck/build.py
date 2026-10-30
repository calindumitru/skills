# Inlines the content scripts into one page: python3 build.py <out.html>
import re, sys, pathlib
here = pathlib.Path(__file__).parent
html = (here / "index.html").read_text()
html = re.sub(r'<script src="(c-[a-z]+\.js)" charset="utf-8"></script>', lambda m: "<script>\n" + (here / m.group(1)).read_text() + "</script>", html)
pathlib.Path(sys.argv[1]).write_text(html)
