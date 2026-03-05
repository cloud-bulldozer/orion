# Orion LLM (AI) Development Policy

Large Language Models (LLMs), including tools like ChatGPT and Claude, can be useful during development. They can speed up onboarding and implementation, but they can also introduce quality, security, and communication risks.

Orion prioritizes maintainable code, clear ownership, and constructive contributor communication. This policy defines how LLMs may be used across Orion repositories and community spaces.

## No Direct LLM-Generated Communication

Do not post LLM output verbatim in:

- GitHub issues or issue comments
- Pull request descriptions, review comments, or commit messages
- Chat, forum, or community posts
- Security reports or vulnerability disclosures

All submissions and discussion must be in your own words and reflect your own understanding.

LLM text is often verbose, generic, or inaccurate. Maintainers may close or reject submissions that are unclear, impersonal, or appear to be pasted directly from an LLM.

### Exceptions

- You may use an LLM for translation support, but you must disclose this (for example: "Translated with an LLM from <language>").
- Maintainer-managed automation or bots may use LLMs for suggestions, but those suggestions are non-authoritative and must be reviewed by humans.

## LLM-Assisted Code Contributions

LLMs may assist with code changes. The contributor remains fully responsible for the result.

### Required Standards

- Follow all expectations in [CONTRIBUTING.md](CONTRIBUTING.md).
- Keep changes focused, minimal, and relevant to the problem.
- Match existing repository style and structure.
- Remove unnecessary generated artifacts, metadata files, and low-value comments.
- Ensure the code builds and tests pass before requesting review.
- Test the behavior you changed and be ready to explain test coverage.

### Ownership and Understanding

You must:

- Review and validate all generated code before submission.
- Explain in your own words what changed and why (in both commit messages and PR descriptions).
- Be able to discuss and defend implementation choices during review.

Submissions that show limited understanding or "vibe-coded" behavior may be rejected.

### Responding to Review Feedback

Do not paste reviewer feedback into an LLM and submit generated responses without analysis.

During review:

- Respond thoughtfully in your own words.
- Make targeted changes that address specific feedback.
- Understand every requested change before updating the PR.

## Maintainer Discretion and Enforcement

Maintainers have final discretion on contribution quality and reviewability. Pull requests may be rejected if they are overly large, difficult to review, poorly structured, or repeatedly fail to meet project standards, regardless of whether LLM tools were used.

Policy violations may result in PR/issue closure, removal of submissions, or contributor bans in severe or repeated cases.

## Golden Rule

Use LLMs as assistants, not as substitutes for understanding, ownership, or engineering judgment.
