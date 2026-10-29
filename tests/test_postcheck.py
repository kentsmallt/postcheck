import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import postcheck as pc

R = pc.load_rules(pc.EXAMPLE_RULES)
GOOD = ("I spent the weekend reading the new validator proposal and testing it on a small node. "
        "Block times dropped on my setup, and the config change took ten minutes. "
        "I still want to see how it behaves under heavy load before moving more stake over to it.")

def test_clean_post_passes():
    fails, _ = pc.check(GOOD, 'original', R, 'en')
    assert fails == []

def test_too_short_fails():
    fails, _ = pc.check('Short post.', 'original', R, 'en')
    assert any('below minimum' in f for f in fails)

def test_ai_words_and_hashtags():
    fails, _ = pc.check(GOOD + ' This is a crucial shift. #crypto', 'original', R, 'en')
    assert any('crucial' in f for f in fails)
    assert any('hashtag' in f.lower() for f in fails)

def test_reply_with_link_fails():
    fails, _ = pc.check('Nice thread, I tested the same thing last week and saw similar results here https://x.y/z', 'reply', R, 'en')
    assert any('must not contain links' in f for f in fails)

def test_duplicate_detection():
    fails, _ = pc.check(GOOD, 'original', R, 'en', history=[('old.txt', GOOD)])
    assert any('duplicate' in f for f in fails)

def test_detect_lang():
    assert pc.detect_lang('這是一篇中文貼文') == 'zh'
    assert pc.detect_lang('hello world') == 'en'

def test_cli_exit_code(monkeypatch, capsys):
    import io
    monkeypatch.setattr(sys, 'stdin', io.StringIO(GOOD))
    assert pc.main(['--type', 'original', '--lang', 'en', '--no-dup']) == 0
    assert 'PASS' in capsys.readouterr().out

def test_question_length_bounds():
    ok = "Which client should I run first?"
    assert 10 <= pc.body_chars(ok) <= 50
    fails, warns = pc.check(ok, 'question', R, 'en')
    assert fails == []
    assert not any('above target' in w for w in warns)
    zh = "你這週會先換哪個客戶端？"
    assert 10 <= pc.body_chars(zh) <= 50
    assert pc.check(zh, 'question', R, 'zh')[0] == []
    fails, _ = pc.check("Why now?", 'question', R, 'en')
    assert any('below minimum' in f for f in fails)
    assert pc.check("Q" * 50, 'question', R, 'en')[0] == []
    fails, warns = pc.check("Q" * 51, 'question', R, 'en')
    assert any('above maximum 50' in f for f in fails)
    assert not any('above target' in w for w in warns)
    long = "Which client should I run first if the upgrade slips past the weekend?"
    assert pc.body_chars(long) > 50
    fails, _ = pc.check(long, 'question', R, 'en')
    assert any('above maximum' in f for f in fails)

def test_question_cap_follows_rules_and_defaults_to_50():
    rules = json.loads(json.dumps(R))
    rules['target_max_chars_warn']['question'] = 80
    assert pc.check("Q" * 80, 'question', rules, 'en')[0] == []
    fails, _ = pc.check("Q" * 81, 'question', rules, 'en')
    assert any('above maximum 80' in f for f in fails)
    rules['target_max_chars_warn'].pop('question')
    fails, _ = pc.check("Q" * 51, 'question', rules, 'en')
    assert any('above maximum 50' in f for f in fails)

def test_question_uses_post_link_rules_not_reply_rules():
    text = "Which client should I run first? https://other.example/a"
    fails, _ = pc.check(text, 'question', R, 'en')
    assert any('allow-listed' in f for f in fails)
    assert not any('Replies must not contain links' in f for f in fails)

def test_long_original_warns_instead_of_failing():
    text = GOOD + " " + ("more detail " * 40)
    assert pc.body_chars(text) > R['target_max_chars_warn']['original']
    fails, warns = pc.check(text, 'original', R, 'en')
    assert fails == []
    assert any('above target' in w for w in warns)

def test_watchlist_and_ai_closers_fail():
    samples = [
        "Here's what I'm watching: funding and basis.",
        "here's what I'm watching next.",
        "Key things to watch are funding and basis.",
        "what I'll be watching is the basis.",
        "what I'm watching next is open interest.",
        "I'll keep watching the funding rate.",
        "I'll be watching the basis.",
        "I'll keep an eye on open interest.",
        "I'll continue to watch the basis.",
        "I will keep watching the basis.",
        "接下來我會盯未平倉量。",
        "接下来我会盯着成交量。",
        "接下來我會看資金費率。",
        "接下來我要看的是基差。",
        "我會持續關注這條曲線。",
        "我會持續盯著基差。",
        "我會繼續關注未平倉。",
        "持續關注這段基差。",
        "接下来我会持续盯着基差。",
        "接下來該盯資金費率。",
        "接下來要盯的是基差。",
        "該盯的是資金費率。",
        "要盯的四個水位先放一邊。",
        "值得盯的是基差。",
        "值得觀察的是資金費率。",
        "值得观察的是资金费率。",
        "全看那一側有沒有人按。",
        "能否攔住這一段。",
        "能否拦住这一段。",
        "能不能撐住全看買盤。",
    ]
    for sample in samples:
        fails, _ = pc.check(GOOD + " " + sample, 'original', R, 'en')
        assert any('AI-tone' in f or 'Formulaic closing' in f for f in fails), (sample, fails)

def test_watch_phrase_fails_mid_text_not_only_as_closer():
    for lead in ("I'll keep watching the basis. ", "接下來我會盯未平倉量。"):
        fails, _ = pc.check(lead + GOOD, 'original', R, 'en')
        assert any('AI-tone' in f for f in fails), (lead, fails)

def test_bare_watch_closing_line_fails():
    fails, _ = pc.check(GOOD + "\n全看買盤還在不在。", 'original', R, 'en')
    assert any('Formulaic closing' in f for f in fails)
    fails, _ = pc.check(GOOD + "\n能否把價格留住全看後面的量。", 'original', R, 'en')
    assert any('Formulaic closing' in f or 'AI-tone' in f for f in fails)

def test_plain_watching_is_allowed():
    fails, _ = pc.check(GOOD + " I am watching the logs on that node.", 'original', R, 'en')
    assert fails == []

def test_promo_disclosure_phrases_fail():
    for phrase in ("含推薦連結", "含推荐链接"):
        fails, _ = pc.check(GOOD + phrase, 'original', R, 'en')
        assert any(phrase in f for f in fails)

def test_rule_regexes_compile():
    for key in ('ai_tone_regex', 'tidy_closing_regex', 'en_regex'):
        for rx in R[key]:
            re.compile(rx)

def test_cli_question_type(monkeypatch, capsys):
    import io
    monkeypatch.setattr(sys, 'stdin', io.StringIO("Which client should I run first?"))
    assert pc.main(['--type', 'question', '--lang', 'en', '--no-dup']) == 0
    assert 'PASS' in capsys.readouterr().out
    monkeypatch.setattr(sys, 'stdin', io.StringIO(
        "Which client should I run first if the upgrade slips past the weekend?"))
    assert pc.main(['--type', 'question', '--lang', 'en', '--no-dup']) == 1
    err = capsys.readouterr().out
    assert 'FAIL' in err and 'above maximum' in err
