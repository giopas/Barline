# [Project Name] — Project Charter

> Base template distilled from the workflow, privacy, security, testing and roadmap practices of the [QLC+ Swiss Knife](https://github.com/giopas/qlc-plus-swiss-knife-tool-script) project. Copy this file into a new repo as `PROJECT_CHARTER.md` (or fold sections into `CONTRIBUTING.md`) and fill in the brackets.

## 1. Overview

- **Name:** [project name]
- **Purpose:** [one or two sentences — what it does and who it's for]
- **Status:** [planning / active / maintenance]
- **Author handle on GitHub:** [alias, not your real name, if you want to stay pseudonymous]
- **License / cost:** [e.g. "free and open source, forever"]
- **Built with AI assistance:** [state this openly if true, and which tool]

## 2. Guiding Principles

- Built for [my own use / my own use and the wider community].
- Optimise for being **useful, deterministic and accurate**, not just feature-complete.
- Present the project from the **user's point of view**, not a developer's, in all public-facing writing.
- [Any other standing philosophy — e.g. "always free", "no telemetry", "no accounts required"]

## 3. Privacy & Identity

- [ ] Decide once, up front: real name or pseudonym on GitHub (commits, issues, wiki, forum posts). If pseudonym, use it everywhere consistently, including git history — not just new commits.
- [ ] No references to real/private data in the public repo: no real venues, clients, addresses, device serials, or anything identifying. Use scrubbed or fictional sample data in demos and test fixtures.
- [ ] No confidential or in-progress material gets committed: scratch folders, local notes, AI working folders (e.g. `.claude/`), drafts, credentials, API keys.
- [ ] If something slips through, don't just delete it in a new commit — rewrite history (e.g. `git filter-repo`) so it's actually gone, and note that it happened.
- [ ] Keep a `.gitignore` that excludes local-only folders (venvs, AI assistant folders, scratch/archive dirs) from day one.

## 4. Security

- [ ] No secrets, tokens, or personal file paths in anything committed. Personal paths go only in local notes or chat, never in repo files (README, changelogs, workplans).
- [ ] Decide and record a stance on code signing / notarisation / packaging trust for any distributed binaries (yes, no, or "later if someone asks").
- [ ] If there's a periodic security review, record findings as a dated doc (not committed if it contains sensitive detail, or redacted if it is).
- [ ] State clearly, if an AI assistant has write access to the project, exactly what it can reach (which folders, which app) — don't leave that ambiguous for users or contributors.

## 5. Workflow

- **Branching:** [e.g. feature branches, merged locally with `--ff-only`, tagged on release; PRs only if collaborating with others]
- **Local-first habit:** update the local working copy → test locally → then push. Never push untested changes.
- **Push handover:** if the AI/agent environment can't reach GitHub directly (DNS/SSH blocked, sandboxed, etc.), it prepares the exact commands and hands them to you to run yourself, e.g.:
  ```
  cd <repo path> && git status --short
  git checkout main && git merge --ff-only feat/x.y.z && git tag vX.Y.Z && git push origin main vX.Y.Z
  ```
- **Continuity log:** keep a living `WORKPLAN.md` (or similar) that every session appends to as work proceeds — what changed, what's next — so work can resume safely if a session is cut short, regardless of who or what is doing the work.
- **Increments:** when working in constrained sessions (time, token budget, etc.), do complete, documented increments. Never leave a change half-done; finish a coherent step or don't start it.

## 6. Testing

- [ ] Test locally on the real target environment before every push (e.g. the actual app/platform, not just unit tests).
- [ ] Track test coverage informally if nothing fancier exists — know roughly how many test files/cases exist and what they cover.
- [ ] New features get at least a manual smoke test on the primary platform before being called done.

## 7. Documentation Standards

- **README:** project presentation only — what it is, why it exists, how to get started. No changelog content; link out to `CHANGELOG.md` instead.
- **Tone:** plain, clear language. Avoid AI-sounding prose (no forced triads, no "not just X but Y", no stock transitions, minimal em-dashes). Write like you'd explain it to a person, not like marketing copy.
- **No version-specific teasers** on evergreen pages (e.g. no "New in v2.3!" baked into a start page that will go stale).
- **Translations:** if the project is localised, every commit that changes or adds UI strings must update all language files in the same commit — don't let translations drift.
- **Release/forum posts:** draft these as needed, but keep them out of the repo itself if they're one-off announcements rather than ongoing docs (or put them in a clearly-local, not-committed folder).

## 8. Roadmap & Versioning

- **Versioning scheme:** [e.g. semver — MAJOR.MINOR.PATCH]
- **Roadmap home:** `WORKPLAN.md` (or `ROADMAP.md`) is the single source of truth for what's done, in progress, and planned — updated as you go, not reconstructed after the fact.
- **Milestones:** decide what counts as a "milestone" release (e.g. worth its own announcement/forum post) vs. a routine point release.
- **Wishlist → committed:** keep a running wishlist; when an item is scheduled, move it into the roadmap with a target version.

## 9. Licensing & Monetisation

- **License:** [MIT / GPL / other]
- **Cost to users:** [free / free forever / paid]
- **Donations:** [accepted directly / redirected to an upstream dependency or related project / not accepted]

## 10. Suggested Repo Skeleton

```
/
├── README.md                 # presentation only, no changelog
├── CHANGELOG.md
├── WORKPLAN.md                # living roadmap + session log (don't commit if it contains private paths)
├── LICENSE
├── .gitignore                 # venvs, AI working folders, scratch/archive dirs, local-only configs
├── src/ (or equivalent)
├── tests/
├── wiki/                      # if using a separate GitHub wiki repo
└── claude/ (or .ai-notes/)    # local-only working docs for AI-assisted sessions — not committed
```

---

*Adapt freely — this is a starting point, not a checklist to follow blindly. Drop sections that don't apply (e.g. localisation, packaging) and add project-specific ones (e.g. hardware compatibility notes, data formats).*
