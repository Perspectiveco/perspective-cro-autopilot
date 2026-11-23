---
description: Run this week's CRO Autopilot pass over every enrolled Perspective funnel: read running tests, call winners, ship them, find the next leak, start the next test, update the learnings log, write the run report.
---

Use the `cro-autopilot` skill and run the weekly loop for every funnel enrolled in `.cro-autopilot/config.json`. If there is no config yet, run the first-run setup from the skill instead. Honor the configured trust mode (review: ask before starting or ending an experiment; auto: act on the script's verdict, ask on lean calls). End with the run report from the skill, saved under `.cro-autopilot/reports/` and shown in full.

$ARGUMENTS
