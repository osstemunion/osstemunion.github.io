"""미리보기용 빌더.

GitHub Pages는 Jekyll로 사이트를 자동 생성하므로 실제 운영에는 이 파일이 필요 없습니다.
Jekyll을 설치할 수 없는 환경에서 결과물을 미리 보기 위해, Jekyll과 같은 규칙
(레이아웃, include, _data, _posts, 기본값, 고유주소)으로 정적 HTML을 만듭니다.

사용법: python3 tools/preview_build.py <사이트폴더> <출력폴더>
"""
import datetime as dt
import os
import re
import shutil
import sys

import markdown
import yaml
from liquid import Environment, FileSystemLoader

SRC, OUT = sys.argv[1], sys.argv[2]
FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def split_fm(text):
    m = FM.match(text)
    if not m:
        return None, text
    return (yaml.safe_load(m.group(1)) or {}), text[m.end():]


def jekyll_includes(src):
    # Jekyll: {% include header.html %}  ->  python-liquid: {% include 'header.html' %}
    return re.sub(r"{%-?\s*include\s+([\w./-]+)\s*-?%}", r"{% include '\1' %}", src)


md = lambda s: markdown.markdown(s, extensions=["extra", "sane_lists"])

config = yaml.safe_load(read(os.path.join(SRC, "_config.yml")))
data = {}
for fn in sorted(os.listdir(os.path.join(SRC, "_data"))):
    if fn.endswith((".yml", ".yaml")):
        data[fn.rsplit(".", 1)[0]] = yaml.safe_load(read(os.path.join(SRC, "_data", fn)))

env = Environment(loader=FileSystemLoader(os.path.join(SRC, "_includes")))


def relative_url(*args, **_kw):
    value = args[-1]
    v = str(value)
    return v if v.startswith("/") else "/" + v


def to_dt(v):
    if isinstance(v, dt.datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day)
    return dt.datetime.fromisoformat(str(v).replace(" +", "+")).replace(tzinfo=None)


def date_filter(_ctx, value, fmt, **_kw):
    return to_dt(value).strftime(fmt)


env.filters["relative_url"] = relative_url
env.filters["markdownify"] = lambda _c, v, *a, **k: md(str(v or ""))
env.filters["date"] = date_filter

layouts = {}
for fn in os.listdir(os.path.join(SRC, "_layouts")):
    fm, body = split_fm(read(os.path.join(SRC, "_layouts", fn)))
    layouts[fn.rsplit(".", 1)[0]] = (fm or {}, jekyll_includes(body))


def defaults_for(kind):
    vals = {}
    for d in config.get("defaults", []):
        if d.get("scope", {}).get("type", kind) == kind:
            vals.update(d.get("values", {}))
    return vals


# ---- 글(_posts) ----
posts = []
for fn in sorted(os.listdir(os.path.join(SRC, "_posts"))):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})-(.+)\.(md|markdown|html)$", fn)
    if not m:
        continue
    fm, body = split_fm(read(os.path.join(SRC, "_posts", fn)))
    page = defaults_for("posts")
    page.update(fm or {})
    y, mo, d, slug, ext = m.groups()
    page["date"] = to_dt(page.get("date") or f"{y}-{mo}-{d}")
    url = config["permalink"].replace(":year", y).replace(":month", mo).replace(":day", d).replace(":title", slug)
    page.update(url=url, slug=slug, _body=body, _ext=ext)
    posts.append(page)

posts.sort(key=lambda p: (p["date"], p["slug"]))
for i, p in enumerate(posts):  # Jekyll: previous = 더 오래된 글, next = 더 최근 글
    p["previous"] = {"url": posts[i - 1]["url"], "title": posts[i - 1]["title"]} if i > 0 else None
    p["next"] = {"url": posts[i + 1]["url"], "title": posts[i + 1]["title"]} if i < len(posts) - 1 else None

site = dict(config)
site.update(data=data, time=dt.datetime.now(), posts=list(reversed(posts)))


def render_content(page, body, ext):
    out = env.parse(jekyll_includes(body)).render({"site": site, "page": page})
    return md(out) if ext in ("md", "markdown") else out


# 글 본문을 먼저 만들어 site.posts 의 content 로 쓸 수 있게 합니다.
for p in posts:
    p["content"] = render_content(p, p["_body"], p["_ext"])


def wrap_layout(page, content):
    name = page.get("layout")
    while name:
        lfm, lbody = layouts[name]
        content = env.parse(lbody).render({"site": site, "page": page, "content": content})
        name = lfm.get("layout")
    return content


def relativize(html, out_rel):
    depth = out_rel.count("/")
    prefix = "../" * depth

    def fix(path):
        if path.startswith("//"):
            return path
        path = path[1:]
        if path == "" or path.startswith("#"):
            path = "index.html" + path
        return prefix + path

    html = re.sub(r'((?:href|src)=")(/[^"]*)"', lambda m: m.group(1) + fix(m.group(2)) + '"', html)
    html = re.sub(r"(url=)(/[^\"']*)", lambda m: m.group(1) + fix(m.group(2)), html)
    return html


def write(out_rel, html):
    path = os.path.join(OUT, out_rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(relativize(html, out_rel))


if os.path.exists(OUT):
    shutil.rmtree(OUT)

for p in posts:
    write(p["url"].lstrip("/"), wrap_layout(p, p["content"]))

excluded = set(config.get("exclude", []))
for root, dirs, files in os.walk(SRC):
    rel_root = os.path.relpath(root, SRC)
    dirs[:] = [d for d in dirs if not d.startswith(("_", ".")) and d not in ("tools",)]
    for fn in files:
        rel = os.path.normpath(os.path.join(rel_root, fn))
        if fn.startswith((".", "_")) or rel in excluded:
            continue
        src_path = os.path.join(root, fn)
        if fn.endswith((".html", ".md")):
            fm, body = split_fm(read(src_path))
            if fm is not None:
                page = dict(fm)
                page["url"] = "/" + rel.replace(".md", ".html")
                content = render_content(page, body, rel.rsplit(".", 1)[1])
                write(rel.replace(".md", ".html"), wrap_layout(page, content))
                continue
        dest = os.path.join(OUT, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src_path, dest)

print("built", OUT)
