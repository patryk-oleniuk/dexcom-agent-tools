---
name: analyze-glucose-patterns
description: Use when the user asks how their glucose/blood sugar/CGM/Dexcom has been, wants their time in range, highs and lows, overnight or post-meal patterns, or a quick glucose summary. Requires the `dexcom` MCP server (get_current_glucose, get_glucose, get_glucose_stats).
---

# Analyze glucose patterns

Turns Dexcom CGM data into a short, plain-language read on what happened and what patterns stand out. **Informational only. Never give insulin doses or treatment instructions.** Point the user to their clinician or their own settings instead.

## When to use
- "How's my glucose / sugar?", "what's my number now?"
- "How was last night / today / the last 24h?", "time in range?"
- "Am I going low after workouts?", "what happens after lunch?"

## Steps

1. **Check the server is there.** If the `dexcom` tools aren't available, say so and point to the repo README. Don't guess numbers. If a tool returns a credentials error, tell the user which env var is missing. Never ask them to paste their password into chat.
2. **Pick the window.** Default to the last 24 hours, which is also the most Share keeps. Translate requests like "last night" into ISO timestamps in the user's local timezone, e.g. 22:00 to 07:00. If they ask about anything older than 24 hours, say Share can't reach it.
3. **Get the data.**
   - Right now: `get_current_glucose`. Report the value, the trend arrow, and how old the reading is. If `age_minutes` is over 15, call it stale.
   - Summary: `get_glucose_stats(start, end)` for TIR, TBR, TAR, mean, CV, and GMI.
   - Patterns: `get_glucose(start, end)` for the raw trace.
4. **Interpret.** Use the trace to find:
   - **Lows**: runs below 70 mg/dL (3.9 mmol/L), and especially below 54 (3.0). Give the start time, how long each lasted, and the nadir.
   - **Highs**: runs above 180 (10.0), and especially above 250 (13.9). Give the start time, duration, and peak.
   - **Overnight** (about 00:00 to 06:00 local): did it stay stable, drift, show a dawn rise, or have a nighttime low?
   - **Variability**: CV of 36% or less counts as stable. Above 36% means high variability.
   - **Post-meal**: the CGM can't see meals or insulin. Only describe rises of 50 mg/dL or more within about 2 hours as *possible* meal spikes, and say that meal/insulin events aren't available. If the user tells you when they ate, check from 0 to 3 hours after each meal.
   - **Data quality**: if `coverage_percent` is under 70%, there are sensor gaps. Mention them and note the stats are less reliable.
5. **Compare to consensus targets** (international CGM consensus for adults with T1D) as context, not as a judgment: TIR above 70%, TBR below 4%, under 1% below 54, TAR below 25%, CV of 36% or less.
6. **Write it up.** Keep it short and lead with the answer:
   - One line: current value and trend, if relevant.
   - 3–5 bullets: TIR/TBR/TAR, mean or GMI, the notable lows and highs with times, the overnight pattern.
   - One neutral observation or question, e.g. "two lows after 4 pm, both after rollerblading?"
   - Use the user's units (mg/dL by default, or mmol/L if they asked or the tool returned them).
   - End with a single short line: "From Dexcom Share (unofficial); confirm with your app/fingerstick before acting."

## Don'ts
- Don't invent readings, meals, or insulin data.
- Don't recommend specific doses, corrections, or carb amounts.
- If a reading is low (under 70) or trending down fast, say plainly to treat per their usual plan and check with a fingerstick. Do this before any analysis.
