---
name: lsb-docs
description: Writing documentation, PR descriptions, and research writeups for LandSandBoat and FFXI. Use when drafting or editing anything under docs/, a wiki page, a PR description, or a writeup of what a packet capture showed. Covers sourcing a claim, dating behaviour to an era, keeping retail separate from LSB, marking unverified data, and reporting numbers.
license: MIT
---

# Writing for LSB

Covers `docs/`, wiki pages, PR descriptions, and research writeups.

Handled elsewhere, do not restate:

- Code comments: the `lsb-cpp-style` skill.
- Commit messages and branch structure: the `lsb-commits` skill.
- Sentence mechanics: see [Plain English](#plain-english) at the bottom.

The rules below are about what a sentence has to contain. Almost every documentation failure
in this project is a missing source, a missing era, or retail and LSB blurred together, not a
clumsy sentence.

## Say where it came from

Every claim about game behaviour carries its source. Without one a reader cannot re-derive it
later, and cannot tell a measurement from a guess.

Order of trust:

1. **Packet capture.** Name the capture and what you extracted from it.
2. **Retail observation**, dated, with who made it.
3. **Wiki** (BG, FFXIclopedia, FFO). Useful, often wrong, and sometimes copied from a private
   server that guessed. Never the only source for a number.
4. **Inference** from code or adjacent mechanics. Label it as inference.

Put the source in the sentence, not a footnote:

> Break rate is 12% with no gear, from 1,412 swings across four Abyssea captures.

not:

> Break rate is 12%.

## Date it

FFXI mechanics change. A statement with no era attached will be wrong for somebody. Name the
version update or the era the behaviour belongs to.

When you do not already know, date it against the official version update history rather than
guessing from a wiki page, which usually describes the mechanic as it stands today. The
`ffxi-version-updates` skill does this if you have it installed; it is not shipped here.

## Retail is not LSB

Keep them apart in every sentence:

- What **retail** does: the target.
- What **LSB** does: the current implementation.
- The **gap**: the reason the change exists.

"X works like this" without saying which one is being described is the most common failure in
LSB documentation, and it is invisible to the person writing it.

## Mark what you do not know

Placeholder and unverified rows carry the exact marker `-- Capture needed`, with no
parenthetical. Over 400 rows under `sql/` already use it, so keep the string exact and
greppable rather than inventing a variant.

In prose, state plainly what is unverified instead of hedging every sentence. A short
"Unverified:" note beats "may possibly sometimes".

## Numbers

Give the sample size with the rate. A rate from 12 observations and one from 12,000 are
different claims, and a reader cannot tell them apart from a percentage.

Say how you measured it. A threshold or filter applied while extracting data changes the
quantity being measured, so name the filter. Two independent extractions that agree are worth
more than one careful one.

## Plain English

For sentence-level mechanics (active voice, cutting dead words, avoiding stock phrases, plain
words over inflated ones) use the `orwell-writing` skill rather than restating it here:

<https://github.com/tamdogood/builder-essential-skills/blob/main/skills/orwell-writing/SKILL.md>

MIT licensed, installed separately. It governs how a sentence reads; this skill governs what a
sentence has to contain. They compose.

Two house rules override it:

- No emdash or other ligatures.
- State things directly rather than using "it's not X, it's Y".
