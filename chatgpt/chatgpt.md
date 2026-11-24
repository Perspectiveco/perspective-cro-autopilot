# Running in ChatGPT

## Where the memory lives

Find out which setup you are in before reading any file.

1. **Local folder (the recommended setup).** The ChatGPT desktop app, in a project with a folder from the user's computer attached. That folder is the working directory, and `.cro-autopilot/` in it stays from one chat and one scheduled run to the next, exactly as the skill describes. Nothing extra to do; never ask for the memory file.
2. **No local folder.** ChatGPT on the web or mobile, or a desktop chat without a folder. Files you write are gone after the chat, so the memory travels as one file the user keeps: `cro-autopilot-memory.zip`.
   - **Start of the run:** look for `cro-autopilot-memory.zip` attached to the chat. Unzip it into the working directory so `.cro-autopilot/` exists again, then go on with step 0. If it is missing and the user has run setup before, ask for it once and wait. Never rebuild the config or the test log from chat history or memory; without the file, only a first-time setup is possible.
   - **End of the run:** after the run report (and also when a run stops early after changing any file), zip `.cro-autopilot/` into `cro-autopilot-memory.zip` and hand it to the user as a download with one line: "Keep this file and attach it to next week's run. It holds your settings and the test log." Never end a run that changed a file without handing the file back.

## Scripts

If you cannot run code here, stop before any verdict and tell the user; never compute a verdict by hand.

## What the user says

There are no slash commands in ChatGPT; the user's words pick setup, the weekly run, a client report or a rollout, as in the commands' descriptions.

## Weekly runs

Weekly runs are ChatGPT scheduled tasks. At the end of the first run, offer once to set one up; set it up when the user asks.

- **Local folder:** create a weekly scheduled task in this project, so it runs in the project folder. Tell the user the computer must be on and the ChatGPT app running at that time. Task prompt: "Use the cro-autopilot skill and run this week's CRO pass for every funnel enrolled in .cro-autopilot/config.json. End with the run report."
- **No local folder:** a scheduled run cannot reach the memory file, so set up a weekly reminder instead: "Time for this week's CRO Autopilot run: start a new chat, attach cro-autopilot-memory.zip and say 'run the weekly CRO'." Say why in one line.

In a scheduled run nobody answers questions; follow "Trust modes" in SKILL.md. If ChatGPT pauses a Perspective tool call for approval, list it under "Needs you"; do not retry around it.
