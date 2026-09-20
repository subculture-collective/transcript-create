# Private beta testing protocol

**Status:** operator-pending beta gate (2026-07-23).

This protocol gates the invite-only beta. It does not authorize a public launch.
Participants may report through their moderator or the beta channel; they do not
need a GitHub account. GitHub issues are an internal triage record only.

## Moderated cohort and privacy

Recruit a moderated cohort of **5–8 consenting people**, including frequent
HasanAbi VOD viewers, researchers or clippers, and at least one keyboard or
assistive-technology user. Collect only a pseudonymous participant ID, relevant
experience with VOD research/clipping, and any volunteered access need needed to
run the session. Do not collect protected traits or other demographics that are
not necessary for this test.

Run and record (with separate, affirmative recording consent) these two manual
accessibility passes over all three core tasks:

1. a keyboard-only pass; and
2. a screen-reader pass.

They may be performed by different consenting participants. Automated axe
results and a keyboard-only pass do not replace recorded screen-reader evidence.
Store recordings and notes under the participant's pseudonymous ID and limit
access to the research and triage team.

### Consent and opening script

Read this script before each session, and record the participant's choices:

> Thank you for helping test this archive. We are evaluating whether people can
> find, verify, and cite recorded material; we are not evaluating you.
> Participation is voluntary. You may skip any question, decline recording, take
> a break, or stop the session at any time without giving a reason. We use a
> pseudonymous participant ID and may collect pseudonymous product analytics for
> this study. May we take notes? May we record your screen and audio? You can
> choose either, both, or neither. Please do not share passwords, cookies, OAuth
> codes, API keys, session tokens, or personal information. Do not paste them
> into the product, chat, attachments, or feedback. If you see something you do
> not want recorded, tell me and we will pause or stop. Do you consent to begin?

## Session tasks

Moderators may clarify the scenario but must not give UI navigation or control
instructions. Record the prompt, not a prescribed path.

Every participant completes these core scenarios:

1. **Recent recording availability:** “You want to catch up on a recent recording.
   Find one and explain what material is available for it.”
2. **Quote or topic citation:** “Find a moment where a topic or quote is
   discussed and give someone a timestamped citation they could use to check it.”
3. **Playback and recovery:** “Verify the cited moment in playback. Then try a
   query that does not return what you expected and get back to a useful result.”

Rotate one secondary scenario per participant so the cohort covers each item;
do not require every secondary task from every person:

- compare timeline or opinion-history evidence;
- save or export an every-mention collection;
- inspect account or session controls; or
- complete a core flow using keyboard or assistive technology.

## Measures and session close

For each task, record completion as **unaided**, **assisted**, or **failed**;
task time as diagnostic context (not a speed target); observed path; errors and
recovery; confidence in any timestamped citation; and a 1–7 Single Ease Question
(SEQ) score. Mark exactly what moderator assistance was given.

At the end, ask:

1. “What value, if any, would this archive provide for you?”
2. “What would need to change for you to trust this archive with this kind of task?”

## Defect severity and moderated exit

Use this exact rubric:

- **S0:** security/privacy breach, data loss/corruption, or unrecoverable deploy;
- **S1:** auth, search, timestamp playback, citation, or core ingestion unusable;
- **S2:** major workflow/accessibility degradation with a workaround;
- **S3:** polish, wording, or low-impact documentation issue.

The moderated gate passes only when all of the following are true: zero open S0
or S1 defects; at least 80% unaided completion on **each** core task; median SEQ
of at least 5/7; no repeated common core-task failure; no critical or serious
accessibility finding; and every S2 is accepted with a named owner and target
date. Otherwise, address and re-test the affected task or accessibility pass.

## Invite-only beta and public decision

Invite **20–50 people** only after the moderated gate passes and the deployment
runbook's invite-only ingress and restore evidence gates remain satisfied. Run
internal triage daily; participant reports are relayed by moderators or the beta
channel into internal triage as needed.

Beta exit requires no open S0/S1, current restore evidence, every S2 fixed or
explicitly accepted, and at least **seven consecutive stable days**. For each
stable day, record a passing result for all four named checks:

1. **Health check** — frontend and API health are available to the invite-gated
   beta;
2. **Search-lag check** — search fallback works and observed indexing lag is
   within the approved beta operating limit;
3. **Worker-lease check** — ingestion workers have no unexpected expired or
   stuck lease and retries are progressing; and
4. **Backup check** — the required backup is current and its evidence is
   recorded.

Any S0/S1 or failure of any critical daily check resets the consecutive-stable-day
count to zero. A public launch is a separate, explicit decision after beta exit;
passing this protocol does not make the archive public.

## Internal feedback handling

Use `.github/ISSUE_TEMPLATE/beta-feedback.yml` for structured internal triage,
not as a participant-facing requirement. Attachments require the reporter's
consent and must be reviewed before sharing. Never put cookies, passwords, OAuth
codes, API keys, session tokens, request payloads containing personal data, or
other personal data in an issue, recording, attachment, or support channel.
