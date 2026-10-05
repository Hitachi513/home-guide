#!/usr/bin/env python3
"""Build the translated copies of the guide from index.html (Traditional Chinese, the source).

    python3 tools/build.py            # refresh i18n/strings.json with new paragraphs, then write en/ zh-CN/ ja/ ko/ es/
    python3 tools/build.py --check    # list paragraphs that still miss a translation

Each "leaf" block (a heading, paragraph, list item, note, caption… that holds only inline markup) is one entry in
i18n/strings.json, keyed by its HTML with whitespace collapsed; translations keep the same inline tags (<b>, <kbd>,
<a href>…). Image, link and alt text are handled the same way. Screenshots for a language live in img/<lang>/ and
fall back to img/ when a language has none.
"""
import datetime
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://hitachi513.github.io/home-guide/"  # search engines need absolute addresses
PROJECT = "https://github.com/Hitachi513/mac-homeserver"
OG_LOCALE = {"zh-TW": "zh_TW", "en": "en_US", "zh-CN": "zh_CN", "ja": "ja_JP", "ko": "ko_KR", "es": "es_ES"}
SRC = os.path.join(ROOT, "index.html")
STRINGS = os.path.join(ROOT, "i18n", "strings.json")
LANGS = ["en", "zh-CN", "ja", "ko", "es"]
NAMES = {"zh-TW": "繁體中文", "en": "English", "zh-CN": "简体中文", "ja": "日本語", "ko": "한국어", "es": "Español"}
HTML_LANG = {"zh-TW": "zh-Hant", "zh-CN": "zh-Hans"}
HAN = re.compile(r"[㐀-鿿]")
# elements that can hold a translatable run of text; a block only counts as a leaf if none of these are inside it
TEXTY = {"title", "h1", "h2", "h3", "h4", "p", "li", "figcaption", "summary", "td", "th", "footer", "a", "span", "div", "b", "label", "button"}
BLOCK = {"div", "p", "ul", "ol", "li", "h1", "h2", "h3", "h4", "figure", "table", "tr", "details", "section", "header", "footer", "img", "br-block"}
VOID = {"br", "img", "meta", "link", "input", "hr", "source"}
ATTRS = ("alt", "title", "aria-label", "placeholder")


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def parse(src):
    """Elements as (tag, start of inner, end of inner, attrs text, children-tags) using a tolerant tag scanner."""
    out, stack = [], []
    for m in re.finditer(r"<!--.*?-->|<(/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*)>", src, re.S):
        if m.group(0).startswith("<!--"):
            continue
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if tag in ("script", "style") and not closing:
            continue
        if closing:
            while stack:
                el = stack.pop()
                if el["tag"] == tag:
                    el["end"] = m.start()
                    out.append(el)
                    if stack:
                        stack[-1]["kids"].update(el["kids"] | {tag})
                    break
            continue
        if tag in VOID or attrs.rstrip().endswith("/"):
            if stack:
                stack[-1]["kids"].add(tag)
            continue
        stack.append({"tag": tag, "attrs": attrs, "start": m.end(), "kids": set(), "end": None})
    return out


def script_ranges(src):
    return [(m.start(), m.end()) for m in re.finditer(r"<(script|style)\b.*?</\1>", src, re.S)]


def leaves(src):
    """Translatable leaf blocks: (start, end, key)."""
    skip = script_ranges(src)
    found = []
    for el in parse(src):
        if el["tag"] not in TEXTY or el["end"] is None:
            continue
        if el["kids"] & BLOCK:
            continue
        inner = src[el["start"]:el["end"]]
        if not HAN.search(re.sub(r"<[^>]*>", "", inner)):
            continue
        if any(a <= el["start"] < b for a, b in skip):
            continue
        found.append((el["start"], el["end"], norm(inner)))
    # keep only outermost leaves (an inline <b> inside a leaf <p> is part of the <p>)
    found.sort(key=lambda x: (x[0], -x[1]))
    result, last_end = [], -1
    for s, e, k in found:
        if s >= last_end:
            result.append((s, e, k))
            last_end = e
    return result


def attr_keys(src):
    keys = []
    for m in re.finditer(r'\b(?:%s)="([^"]*)"' % "|".join(ATTRS), src):
        if HAN.search(m.group(1)):
            keys.append(norm(html.unescape(m.group(1))))
    for m in re.finditer(r'<meta name="description" content="([^"]*)"', src):
        keys.append(norm(m.group(1)))
    return keys


def load():
    try:
        with open(STRINGS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def refresh(src):
    old = load()
    keys = [k for _, _, k in leaves(src)] + attr_keys(src)
    new = {k: {l: (old.get(k) or {}).get(l, "") for l in LANGS} for k in dict.fromkeys(keys)}
    os.makedirs(os.path.dirname(STRINGS), exist_ok=True)
    with open(STRINGS, "w", encoding="utf-8") as f:
        json.dump(new, f, ensure_ascii=False, indent=1)
    return new


def switcher(lang, depth):
    up = "../" * depth
    links = []
    for l, name in NAMES.items():
        href = up + ("?lang=zh" if l == "zh-TW" else l + "/")  # ?lang=zh stops the original from redirecting back
        cur = ' aria-current="page"' if l == lang else ""
        links.append(f'<a href="{href or "./"}" hreflang="{HTML_LANG.get(l, l)}" lang="{HTML_LANG.get(l, l)}"{cur}>{name}</a>')
    return '<nav class="langs" translate="no">🌐 ' + " ".join(links) + "</nav>"


def url_of(lang):
    return SITE + ("" if lang == "zh-TW" else lang + "/")


def seo(lang, title, desc):
    """Everything search engines and link previews read: canonical + language versions, Open Graph / Twitter card,
    and structured data. Absolute URLs only (Google ignores relative hreflang)."""
    img = SITE + f"img/og-{lang}.png"
    tags = [f'<link rel="canonical" href="{url_of(lang)}">']
    tags += [f'<link rel="alternate" hreflang="{HTML_LANG.get(l, l)}" href="{url_of(l)}">' for l in NAMES]
    tags.append(f'<link rel="alternate" hreflang="x-default" href="{SITE}">')
    e = lambda v: html.escape(v, quote=True)
    tags += [f'<meta property="og:type" content="article">', f'<meta property="og:site_name" content="Mac Home Server">',
             f'<meta property="og:title" content="{e(title)}">', f'<meta property="og:description" content="{e(desc)}">',
             f'<meta property="og:url" content="{url_of(lang)}">', f'<meta property="og:image" content="{img}">',
             '<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">',
             f'<meta property="og:locale" content="{OG_LOCALE[lang]}">']
    tags += [f'<meta property="og:locale:alternate" content="{OG_LOCALE[l]}">' for l in NAMES if l != lang]
    tags += ['<meta name="twitter:card" content="summary_large_image">', f'<meta name="twitter:title" content="{e(title)}">',
             f'<meta name="twitter:description" content="{e(desc)}">', f'<meta name="twitter:image" content="{img}">']
    ld = {"@context": "https://schema.org", "@type": "TechArticle", "headline": title, "description": desc,
          "inLanguage": HTML_LANG.get(lang, lang), "url": url_of(lang), "image": img,
          "dateModified": datetime.date.today().isoformat(),
          "author": {"@type": "Person", "name": "Hitachi513", "url": "https://github.com/Hitachi513"},
          "about": {"@type": "SoftwareSourceCode", "name": "Mac Home Server", "codeRepository": PROJECT,
                    "programmingLanguage": "Python", "license": "https://opensource.org/licenses/MIT"}}
    tags.append('<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False) + "</script>")
    return "<!--SEO-->" + "".join(tags) + "<!--/SEO-->"


def sitemap():
    today = datetime.date.today().isoformat()
    alt = "".join(f'<xhtml:link rel="alternate" hreflang="{HTML_LANG.get(l, l)}" href="{url_of(l)}"/>' for l in NAMES)
    urls = "".join(f"<url><loc>{url_of(l)}</loc><lastmod>{today}</lastmod>{alt}</url>" for l in NAMES)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">' + urls + "</urlset>\n")


def head_text(page, tag):
    m = re.search(r"<title>(.*?)</title>" if tag == "title" else r'<meta name="description" content="([^"]*)"', page, re.S)
    return html.unescape(m.group(1)) if m else ""


def build_lang(src, lang, tab):
    out, pos, missing = [], 0, []
    for s, e, k in leaves(src):
        out.append(src[pos:s])
        t = (tab.get(k) or {}).get(lang)
        if not t:
            missing.append(k)
        out.append(t or src[s:e])
        pos = e
    out.append(src[pos:])
    page = "".join(out)

    def tr_attr(m):
        v = norm(html.unescape(m.group(2)))
        t = (tab.get(v) or {}).get(lang) if HAN.search(v) else None
        if HAN.search(v) and not t:
            missing.append(v)
        return f'{m.group(1)}="{html.escape(t, quote=True) if t else m.group(2)}"'
    page = re.sub(r'\b(%s)="([^"]*)"' % "|".join(ATTRS), tr_attr, page)
    page = re.sub(r'(<meta name="description" content=")([^"]*)(")', lambda m: m.group(1) + html.escape((tab.get(norm(m.group(2))) or {}).get(lang) or m.group(2), quote=True) + m.group(3), page)
    page = page.replace('<html lang="zh-Hant">', f'<html lang="{HTML_LANG.get(lang, lang)}">', 1)

    # assets one level up; a language's own screenshot when there is one
    def img(m):
        name = m.group(1)
        own = os.path.join(ROOT, "img", lang, name)
        return f'src="../img/{lang}/{name}"' if os.path.exists(own) else f'src="../img/{name}"'
    page = re.sub(r'src="img/([^"]+)"', img, page)
    page = page.replace("<!--LANGS-->", switcher(lang, 1)).replace("<!--ALT-->", seo(lang, head_text(page, "title"), head_text(page, "description")))
    page = re.sub(r"<script id=\"langpick\">.*?</script>", "", page, flags=re.S)
    # a visitor who picks a language here keeps it (the root page won't send them away again)
    page = page.replace("</body>", f'<script>try{{localStorage.setItem("guide-lang","{lang}")}}catch(e){{}}</script>\n</body>', 1)
    return page, missing


def main():
    with open(SRC, encoding="utf-8") as f:
        src = f.read()
    # the original carries the rendered language bar from the last build: put the markers back first
    src = re.sub(r'<nav class="langs".*?</nav>', "<!--LANGS-->", src, flags=re.S)
    src = re.sub(r"<!--SEO-->.*?<!--/SEO-->", "<!--ALT-->", src, flags=re.S)
    src = re.sub(r'(<link rel="alternate"[^>]*>)+', "<!--ALT-->", src)
    tab = refresh(src)
    if "--check" in sys.argv:
        miss = [k for k, v in tab.items() if any(not v.get(l) for l in LANGS)]
        print(f"{len(tab)} paragraphs, {len(miss)} missing a translation")
        for k in miss[:40]:
            print("  " + k[:120])
        sys.exit(1 if miss else 0)
    for lang in LANGS:
        page, missing = build_lang(src, lang, tab)
        os.makedirs(os.path.join(ROOT, lang), exist_ok=True)
        with open(os.path.join(ROOT, lang, "index.html"), "w", encoding="utf-8") as f:
            f.write(page)
        print(f"{lang}: written, {len(set(missing))} untranslated")
    # the Chinese original gets the same switcher and alternates (in place, idempotent)
    root = src.replace("<!--LANGS-->", switcher("zh-TW", 0)).replace("<!--ALT-->", seo("zh-TW", head_text(src, "title"), head_text(src, "description")))
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(root)
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap())


if __name__ == "__main__":
    main()
