# postcheck

Deterministic, rule-based pre-publish checks for social media posts (X/Twitter-style), supporting English and Chinese (Traditional / Simplified). No LLM calls, no network, no dependencies beyond the Python standard library.

I use it as a final gate in a semi-automated posting workflow: drafts are piped in, and the post only goes out on `PASS`.

## What it checks

| Area | Checks |
|---|---|
| Links | Replies may not contain links. Originals/quotes may contain only allow-listed links, once, as a bare URL on the last line, and the body must mention a configured keyword. |
| Banned markers | Configurable banned phrases, cashtags (`$XXX`), hashtags, and brand names that look like domains (e.g. `foo.io`, which X auto-links). |
| Length | Min / target-max character counts for originals and quotes (over target warns). Questions have a hard minimum and a hard maximum; going over the maximum fails. Replies use a character range (Chinese) or a word range (English). |
| AI tone | Lists and regexes of stock "AI-sounding" phrases in Chinese and English (e.g. "crucial", "delve", "not X, but Y", "here's what I'm watching", "接下來我會盯"), meta/process commentary, and formulaic closing lines. |
| Style | No em dashes, no bold markdown headings; Mainland-Chinese wording flagged in Traditional Chinese posts. |
| Density | Max numbers per sentence (dates, hex addresses and @handles ignored), max sentences per paragraph, max uses of approximation words. |
| Duplicates | Compares against recent posts in a history folder using 3-word (English) / 4-char (Chinese) n-gram containment, and flags identical openings. |

`FAIL` blocks publishing; `WARN` is informational.

## Install

```bash
git clone https://github.com/kentsmallt/postcheck.git
cd postcheck
cp rules.example.json rules.json   # edit to taste
```

Python 3.8+. Tests need `pytest` (`pip install -r requirements-dev.txt`).

## Usage

```bash
python3 postcheck.py --type original --lang en --history ./history < draft.txt
```

| Option | Meaning |
|---|---|
| `--type` | `original`, `quote`, `reply`, `own-reply`, `question` (required) |
| `--lang` | `en`, `zh`, `zh-hans`; auto-detected from CJK ratio if omitted |
| `--rules` | Rules JSON; defaults to `rules.json`, falling back to `rules.example.json` |
| `--history` | Folder of recently published posts (`*.txt`, `*.md`) for duplicate checks |
| `--exclude` | A file in the history folder to skip (when re-checking an old post) |
| `--no-dup` | Skip duplicate checks |

Exit code `0` = PASS, `1` = FAIL, so it drops straight into shell scripts or CI.

## Example output

```
$ echo "This is a crucial update for the landscape. #web3" | python3 postcheck.py --type original --lang en --no-dup
FAIL No hashtags: ['#web3']
FAIL Body is 41 chars, below minimum 150
FAIL English AI word/phrase: "crucial"
FAIL English AI word/phrase: "landscape"
```

It can also be used as a library:

```python
import postcheck
fails, warns = postcheck.check(text, "original", postcheck.load_rules())
```

## Design notes

- **Deterministic over clever.** Every rule is a string list or regex in JSON, so results are reproducible and cheap, and the check can run before any (paid) model review.
- **Rules are data.** New phrases go into `rules.json` without touching code; your personal `rules.json` is git-ignored.
- **Containment, not similarity.** Duplicate detection measures how much of the *new* draft is already in an old post, which catches rewrites of a single earlier post.
- **Language-aware.** Chinese uses character n-grams and full-width punctuation for sentence splitting; English uses word n-grams.

## Tests

```bash
python3 -m pytest -q
```

## License

MIT © Kent
