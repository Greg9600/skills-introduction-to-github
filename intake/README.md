# AI intake

Place files in this folder when you want ChatGPT to review them through the GitHub pull-request task.

## First test

1. Add or edit a file in this folder on a separate branch.
2. Open a pull request whose title starts with `[AI intake]`.
3. The ChatGPT event-triggered task reviews the changed files and returns a report in **Scheduled**.

For the first version, the task is read-only: it should summarize files, identify action items, note missing information or risks, and recommend a next step. It should not modify files or merge pull requests.
