# GitHub Walkthrough

Think of GitHub like a giant school notebook for code.

## What each part means

- **Repository** = the full notebook (this project: IRIS).
- **Folder** = chapter in the notebook (like `docs/`, `tests/`).
- **File** = one page with instructions or code.
- **Commit** = a saved checkpoint.
- **Branch** = a parallel version where we try changes safely.
- **Pull Request (PR)** = "please review my changes" request.

## How to read this repo

1. Open `README.md` first (project overview).
2. Open `docs/planning/execution-status.md` to see what is done and what is next.
3. Open `docs/organization/org-architecture-and-sdlc.md` to see who does what.
4. Open `docs/operations/cloud-deployment.md` to understand cloud setup.
5. Open `tests/` to see how quality is checked.

## How to read new changes

1. Go to the latest PR.
2. Click **Files changed**.
3. Green lines are new content, red lines are removed.
4. Read commit message title for the "why".

## How to track updates in your Google Sheet

Create one tab per module:

- `GitHub Walkthrough`
- `Delivery Status`
- `Architecture & Roles`
- `Cloud Deployment`
- `Release Notes`

For each PR, record:

- Date
- PR title
- Files changed
- What was done
- What is next
