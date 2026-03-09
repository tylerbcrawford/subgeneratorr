# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Subgeneratorr, please report it responsibly.

**Email:** Open a [GitHub Security Advisory](https://github.com/tylerbcrawford/subgeneratorr/security/advisories/new) (preferred) or create a private issue.

**Please do not** open a public issue for security vulnerabilities.

## What to Report

- Authentication or authorization bypasses
- API key exposure or leakage
- Container escape or privilege escalation
- Dependency vulnerabilities with known exploits

## API Key Handling

Subgeneratorr handles several API keys (Deepgram, Anthropic, OpenAI, Gemini). These are:

- Stored only in the `.env` file (gitignored)
- Passed to containers via environment variables
- Never exposed to the browser or frontend JavaScript
- Never logged or written to output files

If you find a case where an API key is inadvertently exposed, please report it immediately.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.x     | Yes       |
| < 2.0   | No        |
