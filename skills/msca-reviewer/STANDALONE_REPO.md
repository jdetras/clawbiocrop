# Standalone `msca-reviewer` repository

This directory is a **self-contained, dependency-free skill** that is ready to live in
its own GitHub repository. The full standalone git history (with LICENSE, `.gitignore`,
GitHub Actions CI, and 11 passing tests) is preserved in **`msca-reviewer.bundle`**.

> The session's GitHub integration is permission-scoped to `jdetras/clawbiocrop` and
> cannot create new repositories (`403 Resource not accessible by integration`), so the
> final "create the repo on GitHub" push is the one step that needs your account.

## Create the GitHub repo and push (2 commands)

```bash
# 1. Reconstruct the standalone repo from the bundle (full history included)
git clone skills/msca-reviewer/msca-reviewer.bundle msca-reviewer
cd msca-reviewer

# 2. Create an empty repo on GitHub named "msca-reviewer", then:
git remote add origin git@github.com:<your-user>/msca-reviewer.git
git push -u origin main
```

`gh` users can do step 2 in one line:

```bash
gh repo create msca-reviewer --public --source=. --remote=origin --push
```

## What's inside

```
msca-reviewer/
├── msca_reviewer.py        # CLI entry point (panel orchestrator)
├── reviewers/              # Excellence / Impact / Implementation / Compliance agents,
│                           #   Panel Chair (weighted % grade) and Feedback agent
├── rules/msca_rules.json   # Official criteria, weights, thresholds, formatting, tips
├── examples/               # Synthetic strong + weak demo proposals
├── tests/                  # 11 red/green TDD tests
├── .github/workflows/ci.yml
├── README.md  SKILL.md  LICENSE
```

## Verify before pushing

```bash
cd msca-reviewer
pip install pytest && pytest tests/ -q          # 11 passed
python msca_reviewer.py --demo --output /tmp/msca_demo
```
