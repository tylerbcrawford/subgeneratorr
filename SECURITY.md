# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Subgeneratorr, please report it responsibly.

Open a private [GitHub Security Advisory](https://github.com/tylerbcrawford/subgeneratorr/security/advisories/new). Only the maintainer can see it, and you will get a reply there.

**Please do not** open a public issue for security vulnerabilities.

## What to Report

- Authentication or authorization bypasses
- Cross-site request forgery or other ways a web page can drive the API
- Reading or writing files outside the media directory
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
| 3.x     | Yes       |
| < 3.0   | No        |
