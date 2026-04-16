# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |
| < latest | :x:               |

Only the latest release receives security updates. Upgrade to stay protected.

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Instead, please email **vedanth.vasudev@gmail.com** with:

1. A description of the vulnerability
2. Steps to reproduce
3. The impact you've identified
4. Any suggested fix (optional)

You should receive an acknowledgement within 48 hours. A fix will be prioritised and released as a patch version as soon as possible.

## Scope

devjournal handles API tokens and credentials in its config file. Security concerns include:

- **Token exposure** — config file permissions, log redaction, memory handling
- **Injection** — JQL injection, URL manipulation, command injection via git
- **Data leakage** — sensitive content appearing in generated notes

## Security Measures

- Config file permission check warns if `config.yaml` is readable by others
- JQL project keys are validated against `^[A-Z][A-Z0-9_]+$` before interpolation
- API tokens are never logged; Cursor session summaries redact token patterns
- URL components are encoded with `urllib.parse.quote`
- Collector configs are scoped so credentials don't leak between integrations

## Responsible Disclosure

We follow responsible disclosure. If you report a vulnerability, we will:

1. Acknowledge receipt within 48 hours
2. Provide a timeline for a fix
3. Credit you in the release notes (unless you prefer anonymity)
