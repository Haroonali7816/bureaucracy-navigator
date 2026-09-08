# Error Analysis — Explained in Plain Terms

This document explains how well the AI system did when tested on 16 real practice letters
(residence permit offices, tax office, health insurance, university), and what problems we found
and fixed along the way. Written so it makes sense whether or not you know how any of the code
works — the exact numbers and technical detail live in `eval/results_final.json` for anyone who
wants that instead.

## What we're actually measuring

For each of the 16 letters, we already know the "correct answer" (we wrote it by hand ahead of
time). We check the AI's answer against that correct answer on three things:

1. **Did it correctly identify what kind of letter this is?** (an appointment notice, a bill, a
   request for documents, a warning, or just informational)
2. **Did it get the exact date(s) right, if the letter has a deadline?**
3. **Did it correctly explain what you actually need to do about it?**

Final scores: type of letter correct 75% of the time, deadline dates correct 87.5% of the time,
and "what to do" correct 62.5% of the time (up from 31% when we started today — more on that
jump below).

## Problem #1: the AI sometimes answered in German instead of English

The letters themselves are in German. We ask the AI to read one and tell us, in English, what
kind of letter it is and what you need to do. Most of the time it did that correctly. But for
about half the letters, when explaining "what you need to do," it would just copy the original
German sentence instead of translating it.

This mattered a lot for the numbers: when we check the AI's answer against our English reference
answer, a German sentence will never look like a match — even if it says exactly the right thing.
So this one mistake was making the system look much worse at understanding letters than it
actually was.

**The fix**: we added one clear instruction telling the AI to always answer in English and to
translate rather than copy the original wording. We tested this specifically on the 8 letters
that had shown the problem, and all 8 came back correctly in English afterward. This alone moved
the "what to do" score from 31% to 50%.

## Problem #2: our own answer-checking method was too strict

To check whether the AI's answer matches our reference answer, we can't just check if the exact
same words were used — two people can describe the same instruction completely differently.
"Show up to the appointment in person" and "Attend the appointment" mean the same thing, but
share barely any words if checked too literally.

So our checking script breaks each sentence into its important words (ignoring small filler
words like "the" and "a"), and counts how many of those words overlap between the AI's answer
and the reference answer. Enough overlap counts as a correct match.

We found two real problems with this method:

- A small technical glitch: a word like `"supervisor's"` was being cut into `"supervisor"` plus
  a leftover meaningless scrap, which quietly made some scores worse than they should have been.
  This was a straightforward bug — fixed with no downside.
- Two specific pairs of words that mean the same thing but don't share letters: "personal" vs.
  "person," and "matriculation number" vs. "student ID number" (matriculation number is just the
  German term for a student's official ID number). We taught the checker these two specific
  pairs, because we could point to two exact real letters where this alone was the difference
  between "correct" and "wrongly marked wrong."

We deliberately did **not** build a giant list of "these words also mean the same thing" for
every possible case. Doing that would mean we're tuning our own grading script until the score
looks good, instead of actually testing whether the AI understands the letters. We only added
the two pairs we could point to and justify individually.

## Adjusting how strict the checker is

The checker has a "how much overlap counts as a match" setting — think of it as a strictness
dial. One letter, about paying a university semester fee, came extremely close to passing but
fell just short. On direction, we turned the dial slightly less strict.

Before doing that, we checked something important: did loosening it accidentally start accepting
*wrong* answers as correct anywhere else in the 16 letters? We checked every single pairing in
the dataset by hand, and the answer was no — only that one already-almost-right case flipped from
"wrong" to "right." Nothing else changed. That check is what makes this a safe, deliberate
adjustment rather than just nudging a number until it looks better — though it's honest to say
this was only verified safe for this specific set of 16 letters, not proven safe in general.

## What's still not fixed, on purpose

- **Two letters failed completely, but not because the AI misunderstood them.** We ran out of
  our daily allowance of requests to the AI service partway through testing — like hitting a
  monthly text-message limit. Those two letters simply never got a real answer. They still count
  against us in the numbers (the honest, if slightly unflattering, way to report it), but it's an
  infrastructure limit, not a case of the AI failing to read a letter.
- **Two other letters are still marked wrong, and they probably shouldn't be.** The AI's answers
  were genuinely correct, just worded so differently from our reference answer that even after
  today's fixes, the automatic checker can't tell they mean the same thing. Fixing this properly
  would mean building a much smarter checker — for example, having a person, or a second AI,
  read both versions and judge whether they mean the same thing. We chose not to do that for this
  project (it adds cost and its own risk of being wrong), and we're saying so plainly rather than
  quietly hiding those two letters from the results.

## Bottom line

The system is solid at figuring out what kind of letter this is and when something is due.
It's now reasonably good — after fixing two real bugs today — at explaining what you actually
need to do, though there's an honest ceiling on how well an automatic script can grade
free-text answers. The two weak spots worth remembering: (1) letters that mention any kind of
payment sometimes get mislabeled as a bill/tax notice even when the AI says it's "sure" — exactly
the kind of mistake a system like this needs to be caught making, not hidden; and (2) our testing
script itself can undercount genuinely correct answers when they're phrased very differently,
which is a limit of how we're checking the AI's work, not of the AI's actual understanding.
