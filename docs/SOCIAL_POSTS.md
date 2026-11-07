# SwitchGuard SRE — `#HowISwitch` Social Copy

## X (Twitter) — single post

> AI coding agents in incident channels are a PII leak waiting to happen.
>
> I built SwitchGuard SRE on @SwitchAI: a 2-room airlock, real pytest repro, FlashProve proof verification, and a human-only rollback gate.
>
> 34 tests. One command to reproduce. #HowISwitch
>
> github.com/<your-handle>/switchguard-sre

## X (Twitter) — thread

1/ Putting an AI coding agent in an on-call channel usually means pasting raw customer emails, cards, and JWTs straight into a model context. That is the real blocker for enterprise incident automation. #HowISwitch

2/ SwitchGuard SRE uses Switch AI's declarative templates: `#alerts-intake` (addressing: anyone) for humans, and `#incident-war-room` (addressing: owner-agents) for shell-running agents. The room link is the security boundary. #HowISwitch

3/ Room 1 scrubs PII, secrets, and prompt injections, then forwards a Luhn-valid synthetic fixture. Zero raw bytes cross the link. The ops console proves it live. #HowISwitch

4/ Room 2 reproduces the bug with real pytest, verifies a FlashProve weight commitment + proof digest, and halts. No rollback without a human typing the exact approval phrase. #HowISwitch

5/ 34 automated tests, a 5-case injection/PII eval suite, WCAG 2.2 AA console, and a one-command Docker quickstart. Built for the Flip the Switch hackathon. github.com/<your-handle>/switchguard-sre #HowISwitch

## LinkedIn

> **AI agents in incident response need two things before production: a PII boundary and a trust boundary.**
>
> I built SwitchGuard SRE for the Flip the Switch hackathon on Switch AI. It is a two-room multi-agent workflow:
>
> - `#alerts-intake` accepts raw customer crash reports and scrubs emails, cards, SSNs, JWTs, and prompt injections before anything crosses the room link.
> - `#incident-war-room` runs a deterministic pytest reproduction against the live service, verifies an Anthropic FlashProve weight-commitment and proof digest, and stages a rollback.
> - A human must type `Approved. Roll back to v2.13.2`. Only then does the service return to the healthy release, with an automated postmortem written to the room.
>
> The stack is FastAPI + SQLite WAL + server-rendered ops console, with 34 automated tests and a one-command Docker quickstart. The interesting design decision was making Switch's room topology the permission model: untrusted users can only reach the agent that cannot run shell commands.
>
> Repo: github.com/<your-handle>/switchguard-sre
>
> #HowISwitch #IncidentResponse #SRE #AIAgents #SwitchAI

## Short caption for the 90s video

> Raw PII in, verified rollback out. SwitchGuard SRE on Switch AI: airlock, reproduce, verify, human-approve. #HowISwitch
