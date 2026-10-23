import os, sys
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
