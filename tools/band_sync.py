"""밴드 → 노조소식 자동 가져오기.

밴드 본문에 #홈페이지 가 들어 있는 글만 골라 _posts 에 노조소식 글로 만듭니다.
GitHub Actions(.github/workflows/band-sync.yml)가 매일 실행합니다.

필요한 비밀값(저장소 Settings → Secrets and variables → Actions):
  BAND_ACCESS_TOKEN  밴드 개발자센터에서 발급한 접근 토큰
  BAND_KEY           가져올 밴드의 band_key (비워 두고 한 번 실행하면 로그에 밴드 목록이 나옵니다)

본문 규칙:
  #홈페이지                 → 이 태그가 있는 글만 가져옵니다.
  #활동소식 #교섭소식 #성명  → 노조소식 분류로 씁니다. 없으면 '공지'.
  첫 줄                     → 글 제목
"""
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = os.environ.get("BAND_API_BASE", "https://openapi.band.us")
TOKEN = os.environ.get("BAND_ACCESS_TOKEN", "").strip()
BAND_KEY = os.environ.get("BAND_KEY", "").strip()
ROOT = os.environ.get("SITE_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAX_PAGES = int(os.environ.get("BAND_MAX_PAGES", "3"))

PUBLISH_TAG = "#홈페이지"
CATEGORY_TAGS = {"#공지": "공지", "#활동소식": "활동소식", "#교섭소식": "교섭소식", "#성명": "성명"}
KST = timezone(timedelta(hours=9))

POSTS_DIR = os.path.join(ROOT, "_posts")
IMG_DIR = os.path.join(ROOT, "images", "band")


def log(msg):
    print(msg, flush=True)


def summary(msg):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")


def api_get(path, params):
    params = dict(params, access_token=TOKEN)
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    if data.get("result_code") != 1:
        raise RuntimeError(f"밴드 API 오류 ({path}): {json.dumps(data, ensure_ascii=False)[:300]}")
    return data["result_data"]


def list_bands():
    for path in ("/v2.1/bands", "/v2/bands"):
        try:
            return api_get(path, {}).get("bands", [])
        except Exception as e:  # 한쪽 주소가 막혀 있으면 다른 쪽을 시도합니다.
            last = e
    raise last


def fetch_posts():
    params = {"band_key": BAND_KEY, "locale": "ko_KR"}
    for _ in range(MAX_PAGES):
        data = api_get("/v2/band/posts", params)
        for item in data.get("items", []):
            yield item
        nxt = (data.get("paging") or {}).get("next_params")
        if not nxt:
            break
        params = {k: v for k, v in nxt.items() if k != "access_token"}


def existing_keys():
    keys = set()
    if not os.path.isdir(POSTS_DIR):
        return keys
    for fn in os.listdir(POSTS_DIR):
        with open(os.path.join(POSTS_DIR, fn), encoding="utf-8") as f:
            head = f.read(2000)
        m = re.search(r'^band_post_key:\s*"?([^"\n]+)"?', head, re.M)
        if m:
            keys.add(m.group(1).strip())
    return keys


def clean_text(raw):
    """밴드 본문 표식(<band:refer> 등)을 걷어내고 일반 글로 만듭니다."""
    text = re.sub(r"</?band:[^>]*>", "", raw or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).replace("\r\n", "\n").replace("\r", "\n")


def strip_tags(text):
    tags = [PUBLISH_TAG] + list(CATEGORY_TAGS)
    pattern = "|".join(re.escape(t) for t in sorted(tags, key=len, reverse=True))
    text = re.sub(rf"(?:{pattern})(?![\w가-힣])", "", text)
    lines = [re.sub(r"[ \t]+$", "", l) for l in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def pick_category(text):
    for tag, cat in CATEGORY_TAGS.items():
        if re.search(re.escape(tag) + r"(?![\w가-힣])", text):
            return cat
    return "공지"


def to_html(body):
    """줄바꿈을 살린 문단 HTML. 주소는 링크로 바꿉니다."""
    url_re = re.compile(r"(https?://[^\s<]+)")
    paras = []
    for block in re.split(r"\n\s*\n", body.strip()):
        lines = []
        for line in block.split("\n"):
            esc = html.escape(line)
            esc = url_re.sub(lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener">{m.group(1)}</a>', esc)
            lines.append(esc)
        paras.append("<p>" + "<br>\n".join(lines) + "</p>")
    out = "\n\n".join(paras)
    if "{{" in out or "{%" in out:
        out = "{% raw %}\n" + out + "\n{% endraw %}"
    return out


def safe_slug(post_key):
    return "band-" + hashlib.sha1(post_key.encode("utf-8")).hexdigest()[:10]


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        f.write(r.read())


def yaml_str(s):
    return json.dumps(s, ensure_ascii=False)


def make_post(item):
    raw = clean_text(item.get("content", ""))
    category = pick_category(raw)
    body = strip_tags(raw)
    lines = body.split("\n")
    first = next((l.strip() for l in lines if l.strip()), "")
    if not first:
        first = "밴드 소식"
    if len(first) <= 80:
        title = first
        idx = next(i for i, l in enumerate(lines) if l.strip() == first) if body else 0
        body = "\n".join(lines[idx + 1:]).strip()
    else:
        title = first[:78].rstrip() + "…"

    created = datetime.fromtimestamp(int(item.get("created_at", 0)) / 1000, tz=KST)
    slug = safe_slug(item["post_key"])
    filename = f"{created:%Y-%m-%d}-{slug}.md"

    images = []
    photos = [p for p in (item.get("photos") or []) if p.get("url") and not p.get("is_video_thumbnail")]
    if photos:
        os.makedirs(IMG_DIR, exist_ok=True)
    for i, p in enumerate(photos, 1):
        ext = os.path.splitext(urllib.parse.urlparse(p["url"]).path)[1].lower()
        ext = ext if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp") else ".jpg"
        name = f"{slug}-{i}{ext}"
        try:
            download(p["url"], os.path.join(IMG_DIR, name))
            images.append(f"/images/band/{name}")
        except Exception as e:
            log(f"  사진 {i} 내려받기 실패: {e}")

    parts = [
        "---",
        f"title: {yaml_str(title)}",
        f"date: {created:%Y-%m-%d %H:%M:%S} +0900",
        f"category: {category}",
        f'band_post_key: "{item["post_key"]}"',
        "source: 밴드",
        "---",
        "",
        to_html(body) if body else "",
    ]
    for src in images:
        parts += ["", f'<p><img src="{{{{ \'{src}\' | relative_url }}}}" alt="{html.escape(title)} 사진"></p>']
    return filename, "\n".join(parts).rstrip() + "\n"


def main():
    if not TOKEN:
        print("BAND_ACCESS_TOKEN 비밀값이 아직 없어 밴드 연동을 건너뜁니다. 저장소 Settings → Secrets and variables → Actions 에 넣으면 다음 실행부터 동작합니다.")
        sys.exit(0)

    if not BAND_KEY:
        log("BAND_KEY 비밀값이 없어 내 밴드 목록만 보여드립니다. 노조 밴드의 band_key 를 BAND_KEY 비밀값에 넣어 주세요.")
        summary("### 내 밴드 목록\n\n| 밴드 이름 | band_key |\n|---|---|")
        for b in list_bands():
            log(f"  {b.get('name')}  →  {b.get('band_key')}")
            summary(f"| {b.get('name')} | `{b.get('band_key')}` |")
        return

    os.makedirs(POSTS_DIR, exist_ok=True)
    have = existing_keys()
    added, seen, tagged = [], 0, 0
    for item in fetch_posts():
        seen += 1
        content = clean_text(item.get("content", ""))
        if not re.search(re.escape(PUBLISH_TAG) + r"(?![\w가-힣])", content):
            continue
        tagged += 1
        if item.get("post_key") in have:
            continue
        filename, text = make_post(item)
        with open(os.path.join(POSTS_DIR, filename), "w", encoding="utf-8") as f:
            f.write(text)
        have.add(item["post_key"])
        added.append(filename)
        log(f"  새 글: {filename}")

    msg = f"밴드 글 {seen}개 확인, #홈페이지 글 {tagged}개, 새로 올린 글 {len(added)}개"
    log(msg)
    summary(f"### 밴드 → 노조소식\n\n{msg}\n" + "".join(f"\n- `{a}`" for a in added))


if __name__ == "__main__":
    main()
