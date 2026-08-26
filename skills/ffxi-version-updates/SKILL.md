---
name: ffxi-version-updates
description: >
  Search official FFXI version update and patch notes in both English and Japanese, 2002 to
  present. Use whenever a question is about WHEN or HOW something changed in retail FFXI:
  "when was X added", "when did Y get nerfed or buffed", "what changed in the March 2014
  update", "was this mechanic in the game at era Z", "when did the cap on X get raised",
  "when was zone/job/item/system N introduced". Also use to date a mechanic for era accurate
  private server work (LSB, HorizonXI, 75 cap projects), and whenever the English patch note
  is vague, ambiguous, or reads like a bad translation, since the Japanese original is the
  source text and is kept alongside.
license: MIT
compatibility: Requires Python 3.9+ and network access on first run to download the archive.
---

# FFXI Version Update Notes (EN + JA)

Official patch notes as plain text, one file per update per language: about 2200 notes,
1260 EN and 954 JA, spanning 2002-07-09 to the present. Both languages run the whole range.

**The corpus is not shipped with this skill.** `notes/` and `raw/` are built locally and are
deliberately not in git: the text is Square Enix's, not ours to redistribute. Build it once,
then keep it current.

Paths below are relative to this skill's own directory. Run `build.py` from there.

## Step 0: does the corpus exist?

```bash
head -1 notes/INDEX.md
# -> 2214 notes, oldest 2002-07-09, newest 2026-08-18
```

If that fails, build it. One command, a couple of minutes, mostly a 30MB download:

```bash
python build.py
```

## Step 1: is it current?

SE ships a version update around the 10th of every month. Rebuild if any of these hold:

- the newest note is from a month before the current one, and today is past the 10th
- the newest note is more than about 40 days old
- the question is about "recently", "the latest update", "current retail", or a named month
  you do not see in `INDEX.md`
- you searched, found nothing, and the feature sounds recent

```bash
python build.py --refresh
```

Skip it for questions about a date already in `INDEX.md`, since the past does not change.

## Corpus layout

Filenames are `YYYY-MM-DD-<lang>-<slug>.txt`, so the date and language of every grep hit are
free, and the EN and JA files for one update share a date prefix. Each file opens with
`# title`, `# date:`, `# lang:`, `# category:` and `# source:` (the original URL).
`notes/INDEX.md` is the full date/lang/title/file table.

### Coverage

| Source | Records | Coverage |
|---|---|---|
| polnews JP | 762 | playonline.com/ff11 news, 2003 to present |
| polnews US | 753 | playonline.com/ff11us news, 2003 to present |
| forum | 364 | forum.square-enix.com, EN subforum 84 and JA subforum 15, 2011 to present |
| topics | 290 | playonline.com/pcd2 version update detail articles, 2006 to 2013 |
| legacy | 45 | playonline.com comnews and updateus, 2002 to 2007 |

**Japanese runs 2002 to the present with no gap**, so the JA cross-check below works for any
era, including the 75 cap years.

Coverage is not one-to-one. Of the version update dates, 456 carry both languages, 647 are EN
only and 254 are JA only. A missing counterpart is normal rather than a sign you searched
wrong: SE did not publish every notice in both markets. Check for the paired file, and if there
is none, say so instead of assuming the other language holds a better answer.

Some JA notes carry a machine translation appended and clearly marked, including the 2002-2003
pages that predate the North American release. Treat those translations as a reading aid, never
as a citable source: quote the Japanese and say it is your own reading of it.

## Searching

Prefer the Grep tool with `path` set to this skill's `notes/` and `output_mode: content`.

```bash
# which updates mention a thing; the filename dates and tags each hit
grep -rli 'chocobo racing' notes/

# with context
grep -rin -C3 'fields of valor' notes/ | head -60

# English only, Japanese only
grep -rin 'weapon skill' notes/*-en-*.txt
grep -rn  'ウェポンスキル'  notes/*-ja-*.txt

# both languages for one update
ls notes/2020-10-12-*
```

Tips:

- **First mention is the introduction date.** Sort hits by filename; the earliest is usually
  when it shipped.
- Try several phrasings. SE's EN wording drifts across eras ("Fields of Valor" vs "training
  regimes", "merit points" vs "limit points").
- Terms that hit hundreds of files ("item", "adjusted") are useless. Grep the distinctive noun.
- Cite the date and the `# source:` URL from the file header.

## Cross-checking the Japanese

The Japanese post is the original. The English one is a localization, and it is regularly
vague, wrong, or drops a qualifier. Check the JA file whenever:

- the EN note is ambiguous about a number, a rate, a cap, or a condition
- the EN note says something hand-wavy ("adjusted", "made easier") with no specifics
- EN and observed retail behaviour disagree
- the mechanic matters for an implementation

Workflow: find the date from the EN hit, open `notes/<date>-ja-*.txt`, find the same bullet
(the JA post uses the same section order), then report both and say which one you are trusting.

Useful JA search terms:

| JA | EN | JA | EN |
|---|---|---|---|
| 追加 | added | 変更 / 調整 | changed / adjusted |
| 修正 | fixed | 不具合 | bug |
| 上方修正 / 下方修正 | buffed / nerfed | 緩和 | relaxed, eased |
| 上限 | cap, maximum | 確率 | rate, chance |
| 効果 / 効果時間 | effect / duration | 再使用時間 | recast |
| 発動 | trigger, proc | 入手 | obtain |
| 報酬 | reward | 経験値 | EXP |
| ジョブ / アビリティ / 特性 | job / ability / trait | 魔法 / ウェポンスキル | magic / weapon skill |
| 装備 / 武器 / 防具 | equipment / weapon / armor | アイテム / 素材 | item / material |
| クエスト / ミッション | quest / mission | エリア / モンスター | area / monster |
| 合成 / スキル | synthesis / skill | 釣り / 栽培 / 採掘 / 伐採 / 刈り取り | fishing / gardening / mining / logging / harvesting |
| チョコボ / モグハウス | chocobo / Mog House | 競売 / 取引 | auction house / trade |

Section headers in JA posts, in order: `イベント関連`, `バトル関連`, `アイテム関連`,
`システム関連`, `不具合修正`, `確認されている不具合`. These map one for one onto EN's
Event-related, Battle-related, Item-related, System-related, Resolved Issues and Known Issues,
so the Nth bullet under a JA header is the Nth bullet under the matching EN header.

## Where the data comes from

[Frankie-hz/ffxiupdates](https://github.com/Frankie-hz/ffxiupdates) (MIT) does the hard part:
it enumerates every official news id by brute force rather than trusting wiki catalogs, sweeps
both the JP and US playonline news paths, crawls the EN and JA version update subforums, and
publishes one normalised `all.jsonl` with a `lang`, `url` and `category` on every record.

`build.py` downloads that file to `raw/`, keeps the records in the Version Update, Update
Details and Updates categories (about 2200 of 12500; the rest is login server status and
maintenance notices that bury real hits), flattens the HTML to text, and writes `notes/`.

Report corpus gaps upstream rather than working around them here.

```bash
python build.py --source /path/to/ffxiupdates   # render from a local clone
python test_build.py                            # tests, no network needed
```
