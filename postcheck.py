#!/usr/bin/env python3
"""postcheck: deterministic pre-publish checks for social media posts (no LLM calls).

Usage:
    python3 postcheck.py --type {original,quote,reply,own-reply} [--lang zh|zh-hans|en]
                         [--rules FILE] [--history DIR] [--exclude FILE] [--no-dup] < draft.txt

Prints WARN lines (informational) and FAIL lines. Exit code 0 = PASS, 1 = FAIL.
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RULES = os.path.join(HERE, 'rules.json')
EXAMPLE_RULES = os.path.join(HERE, 'rules.example.json')
URL_RE = re.compile(r'https?://\S+|www\.\S+')
DATE_RE = re.compile(
    r'(\d{4}\s*年\s*)?\d{1,2}\s*月\s*\d{1,2}(\s*[、,–\-到至]\s*\d{1,2})*\s*日|\d{4}\s*年'
    r'|\d{1,2}/\d{1,2}(/\d{2,4})?'
    r'|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2}(, \d{4})?')
CASHTAG_RE = re.compile(r'(?<![\w&])\$[A-Za-z]{2,10}\b')


def load_rules(path=None):
    if path is None:
        path = DEFAULT_RULES if os.path.exists(DEFAULT_RULES) else EXAMPLE_RULES
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def detect_lang(text):
    cjk = len(re.findall(r'[\u4e00-\u9fff]', text))
    return 'zh' if cjk > len(text) * 0.15 else 'en'


def body_chars(text, links=()):
    for link in links:
        text = text.replace(link, '')
    return len(re.sub(r'\s', '', text))


def sentences(text):
    return [s for s in re.split(r'(?<=[。！？!?])|(?<=\.)\s+|\n', text) if s and s.strip()]


def ngrams(text, lang):
    text = URL_RE.sub('', text).lower()
    if lang == 'en':
        w = re.findall(r"[a-z0-9']+", text)
        return {' '.join(w[i:i + 3]) for i in range(len(w) - 2)}
    s = re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', text)
    return {s[i:i + 4] for i in range(len(s) - 3)}


def count_numbers(s):
    """Count numeric tokens, ignoring hex addresses, @handles and dates."""
    s = re.sub(r'0x[0-9a-fA-F…\.]+', ' ', s)
    s = re.sub(r'@\w+', ' ', s)
    s = DATE_RE.sub(' ', s)
    return len(re.findall(r'\d+(?:[.,:/\-]\d+)*', s))


def opening(text, k):
    first = URL_RE.sub('', text.strip().split('\n')[0])
    return re.sub(r'[\s@\W_]', '', first)[:k]


def recent_texts(history_dir, n, exclude=None):
    """Load the n most recent *.txt / *.md posts from history_dir."""
    if not history_dir or not os.path.isdir(history_dir):
        return []
    files = sorted(glob.glob(os.path.join(history_dir, '*.txt')) + glob.glob(os.path.join(history_dir, '*.md')),
                   key=os.path.getmtime, reverse=True)
    ex = os.path.abspath(exclude) if exclude else None
    out = []
    for f in files:
        if ex and os.path.abspath(f) == ex:
            continue
        try:
            with open(f, encoding='utf-8') as fh:
                out.append((os.path.basename(f), fh.read()))
        except OSError:
            continue
        if len(out) >= n:
            break
    return out


def check(text, post_type, rules, lang=None, history=()):
    """Run all checks. Returns (fails, warns) as lists of strings."""
    R = rules
    t = text.strip()
    lang = lang or detect_lang(t)
    is_reply = post_type in ('reply', 'own-reply')
    allowed = [u.rstrip('/') for u in R.get('allowed_links', [])]
    fails, warns = [], []
    F, W = fails.append, warns.append
    low = t.lower()
    lines = [l for l in t.split('\n') if l.strip()]
    no_url = URL_RE.sub('', t)

    # Links
    urls = URL_RE.findall(t)
    if is_reply and urls:
        F(f'Replies must not contain links: {urls}')
    if not is_reply:
        other = [u for u in urls if u.rstrip('/') not in allowed]
        if other:
            F(f'Only allow-listed links are permitted: {other}')
        for link in allowed:
            if link in t:
                if lines[-1].strip().rstrip('/') != link:
                    F('Allow-listed link must be a bare URL on the last line')
                if t.count(link) > 1:
                    F('Allow-listed link may appear only once')
                kw = R.get('pinned_link_keyword')
                if kw and kw.lower() not in low:
                    F(f'Link present but the post body never mentions "{kw}"')

    # Banned markers
    for w in R.get('banned_always', []):
        if w.lower() in low:
            F(f'Banned phrase: "{w}"')
    tags = CASHTAG_RE.findall(t)
    if tags:
        F(f'No cashtags: {tags}')
    hashtags = re.findall(r'(?<![\w&/])#[^\W\d][\w]*', no_url)
    if hashtags:
        F(f'No hashtags: {hashtags}')
    tld = '|'.join(R.get('domain_tlds', []))
    if tld:
        dom = re.findall(rf'\b[A-Za-z0-9-]+\.(?:{tld})\b', no_url, re.I)
        if dom:
            F(f'Brand names that look like domains get auto-linked: {dom}')

    # Length
    n = body_chars(t, allowed)
    if post_type in R.get('min_chars', {}):
        if n < R['min_chars'][post_type]:
            F(f'Body is {n} chars, below minimum {R["min_chars"][post_type]}')
        if n > R['target_max_chars_warn'][post_type]:
            W(f'Body is {n} chars, above target {R["target_max_chars_warn"][post_type]}')
    if is_reply:
        if lang == 'en':
            wc = len(re.findall(r"[A-Za-z0-9'’]+", t))
            lo, hi = R['reply_en_words']
            if wc < lo:
                F(f'English reply has {wc} words, fewer than {lo}')
            elif wc > hi:
                W(f'English reply has {wc} words, more than {hi}')
        else:
            lo, hi = R['reply_zh_chars']
            if n < lo:
                F(f'Reply has {n} chars, fewer than {lo}')
            elif n > hi:
                W(f'Reply has {n} chars, more than {hi}')
        nums = len(re.findall(r'\d+(?:[.,:/]\d+)*', no_url))
        if nums > 1:
            W(f'Reply contains {nums} numbers (aim for at most 1)')

    # Wording
    if lang == 'zh':
        bad = [w for w in R.get('mainland_words_for_traditional', []) if w in t]
        if bad:
            F(f'Mainland-Chinese wording in a Traditional Chinese post: {bad}')
    for w in R.get('ai_tone_phrases', []):
        if w in t:
            F(f'AI-tone phrase: "{w}"')
    for rx in R.get('ai_tone_regex', []):
        m = re.search(rx, t, re.M)
        if m:
            F(f'AI-tone pattern: "{m.group(0)}"')
    for w in R.get('process_phrases', []):
        if w in t:
            F(f'Process/meta commentary: "{w}"')
    last = lines[-1] if lines else ''
    if last.strip().rstrip('/') in allowed and len(lines) > 1:
        last = lines[-2]
    for rx in R.get('tidy_closing_regex', []):
        if re.search(rx, last.strip(), re.I):
            F(f'Formulaic closing line: "{last.strip()[-30:]}"')
    if lang == 'en':
        for w in R.get('en_ai_words', []):
            end = r'\b' if not w.endswith(' ') else ' '
            if re.search(r'\b' + re.escape(w.strip()) + end, low):
                F(f'English AI word/phrase: "{w.strip()}"')
        for rx in R.get('en_regex', []):
            m = re.search(rx, low)
            if m:
                F(f'English pattern: "{m.group(0)}"')
    if '—' in t:
        F('No em dashes (— / ——)')
    if re.search(r'\*\*[^*]+\*\*', t):
        F('No bold markdown headings')

    # Numbers and paragraph shape (originals / quotes)
    if not is_reply:
        ap_n = sum(no_url.count(w) for w in R.get('approx_words', []))
        if ap_n > R['max_approx_words']:
            F(f'Approximation words used {ap_n} times (max {R["max_approx_words"]})')
        cap = R['max_numbers_per_sentence']
        for s in sentences(no_url):
            k = count_numbers(s)
            if k >= R.get('numbers_per_sentence_fail', 5):
                F(f'{k} numbers in one sentence (max {cap}): "{s.strip()[:40]}…"')
            elif k > cap:
                W(f'{k} numbers in one sentence (max {cap}, please verify): "{s.strip()[:40]}…"')
        for p in re.split(r'\n\s*\n', no_url):
            splitter = r'(?<=[.!?])\s+' if lang == 'en' else r'(?<=[。！？!?])'
            ss = [s for s in re.split(splitter, p) if s.strip()]
            if len(ss) > R['max_sentences_per_paragraph']:
                F(f'Paragraph has {len(ss)} sentences (max {R["max_sentences_per_paragraph"]}): "{p.strip()[:30]}…"')

    # Duplicate / same-opening detection against recent posts
    g = ngrams(t, lang)
    op = opening(t, R.get('opening_chars', 10))
    for name, txt in history:
        h = ngrams(txt, lang)
        if g and h:
            c = len(g & h) / len(g)
            if c >= R['dup_containment_fail']:
                F(f'Overlaps {c:.0%} with recent post {name}; looks like a duplicate')
            elif c >= R['dup_containment_warn']:
                W(f'Overlaps {c:.0%} with {name}; make sure it is not a rewrite')
        if len(op) >= 6 and opening(txt, R.get('opening_chars', 10)) == op:
            F(f'Same opening as recent post {name}: "{op}"')
    return fails, warns


def main(argv=None):
    ap = argparse.ArgumentParser(description='Pre-publish quality checks for social posts.')
    ap.add_argument('--type', required=True, choices=['original', 'quote', 'reply', 'own-reply'])
    ap.add_argument('--lang', choices=['zh', 'zh-hans', 'en'])
    ap.add_argument('--rules', help='rules JSON (default: rules.json, else rules.example.json)')
    ap.add_argument('--history', help='directory of recent published posts for duplicate checks')
    ap.add_argument('--exclude', help='file in --history to skip (e.g. when re-checking an old post)')
    ap.add_argument('--no-dup', action='store_true', help='skip duplicate checks')
    a = ap.parse_args(argv)
    rules = load_rules(a.rules)
    history = [] if a.no_dup else recent_texts(a.history, rules.get('dup_recent_n', 20), a.exclude)
    fails, warns = check(sys.stdin.read(), a.type, rules, a.lang, history)
    for w in warns:
        print('WARN', w)
    for f in fails:
        print('FAIL', f)
    if fails:
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
