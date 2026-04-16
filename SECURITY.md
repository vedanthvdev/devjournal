# Security Policy

## Supported Versions

Only the latest released version receives security updates. Upgrade to stay protected.

| Version  | Supported          |
| -------- | ------------------ |
| latest   | :white_check_mark: |
| < latest | :x:                |

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Please use one of the following private channels:

1. **Preferred** — GitHub's [private vulnerability reporting](https://github.com/vedanthvdev/devjournal/security/advisories/new)
   (Security tab → "Report a vulnerability"). This keeps the report confidential
   and lets us collaborate on a fix in a draft security advisory.
2. Email **vedanth.vasudev@gmail.com** if you can't use GitHub's flow.

Please include:

1. A description of the vulnerability
2. Steps to reproduce
3. The impact you've identified
4. Any suggested fix (optional)

We aim to acknowledge reports as soon as possible, typically within a few days.
A fix will be prioritised and released as a patch version once triaged.

## Scope

devjournal handles API tokens and credentials in its config file. In-scope concerns:

- **Token exposure** — config file permissions, log redaction, memory handling
- **Injection** — JQL injection, URL manipulation, command injection via git
- **Data leakage** — sensitive content appearing in generated notes

Out of scope: vulnerabilities in third-party services (Jira, GitLab, GitHub, Confluence),
misconfigured user systems, and reports that require physical access to the host.

## Security Measures

- Config file permission check warns if `config.yaml` is readable by others
- JQL project keys are validated against `^[A-Z][A-Z0-9_]+$` before interpolation
- API tokens are never logged; Cursor session summaries redact token patterns
  (GitLab `glpat-`, Atlassian `ATATT`, GitHub `ghp_`/`gho_`/`github_pat_`,
  OpenAI `sk-`, Slack `xoxb-`/`xoxp-`, AWS access keys, bearer tokens, JWTs)
- URL components are encoded with `urllib.parse.quote`
- Collector configs are scoped so credentials don't leak between integrations

## Responsible Disclosure

We follow responsible disclosure. If you report a vulnerability, we will:

1. Acknowledge receipt
2. Share a timeline for a fix
3. Credit you in the release notes (unless you prefer anonymity)
