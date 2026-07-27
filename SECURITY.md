# Security Policy

## Supported versions

Only the latest release is maintained. No backport security patches are made to older versions.

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.**

Email `pooryoricksalmanack@gmail.com` with the subject line `[oneTask security]`. Include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact

I'll acknowledge the report within a few days and work toward a fix. Response time depends on severity and my availability — this is a solo-maintained personal project.

## Scope and expectations

OneTask is a personal, single-user tool. Its threat model is correspondingly limited:

- It is **not** designed to be exposed to the public internet.
- The password mechanism (`ONETASK_PASSWORD`) is basic HTTP Basic Auth — adequate for keeping casual visitors off your home network, not for production hardening.
- There is no multi-user support, rate limiting, or audit logging.

See the [Security section of the README](README.md#security) for the full security model and safe deployment guidance.

## Routine hygiene

- Dependabot monitors dependencies for known CVEs
- Input validation on all TaskWarrior operations
- Secure error pages (no stack traces exposed)
- Debug mode disabled in production
