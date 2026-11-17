# Golden dataset format

One row per call, for all 50 calls.

## How to label

- Label from what you hear. The transcript shows what the agent wrote, which isn't always what was played.
- Don't look at `disposition` or `meta.end_call` in `call.json` until you've finished labelling. They hold what the agent decided.
- Every choice has "Can't tell". Use it when the audio is unclear. Never guess.

## Columns

| Column | What to write |
|---|---|
| Call | `call_01` to `call_50` |
| What happened | Go down the list below and pick the first one that fits |
| Correct outcome | How the call should have ended, given what the customer said. Not what the agent chose |
| Facts the customer gave | Short: their policy (own, company, none), who needs cover, booking or call-back time. Blank if none |
| Sentiment | The customer's mood over the whole call |
| Emotion | From your own list of 3 to 6 labels. Define each one in a line at the top of the file |
| Overall | Good: fine for the client to hear. OK: small issues. Bad: the client would complain, or the customer was wronged |
| First thing wrong: line | Position in `messages`, counting from 1. Only the first problem. Blank if nothing went wrong |
| First thing wrong: what | One sentence on what went wrong |
| Never-rule broken | None, or which one (list below) |

## Allowed values

| What happened | Correct outcome | Sentiment | Overall |
|---|---|---|---|
| Machine or call screener answered | Expert call booked | Positive | Good |
| Heard nothing from the agent | Call later agreed | Neutral | OK |
| Agent's first words came late (over 3 s) | Not interested | Negative | Bad |
| Left during the first line, said nothing | Do not call | Can't tell | Can't tell |
| Said hello or a few words, then left | Voicemail | | |
| Gave a real answer, then left before an ending | Call screener or machine | | |
| Call reached an ending | No outcome: customer left first | | |
| Can't tell | Can't tell | | |

## Never-rules

- Pushed a policy or insurer.
- Gave a premium figure.
- Booked for today, or outside 9 am to 9 pm.
- Booked without a clear yes.
- Asked for PAN, Aadhaar, bank details or OTP.
- Denied being an AI.

## Reply wait check

On a separate sheet, for 20 calls: pick one reply per call and write the customer's last word time, the agent's first audible sound time, both from the recording, and the gap in seconds.
