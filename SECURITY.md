# Security policy

Genesis is experimental, intended for a trusted local environment, and has no
production support guarantee or authentication. Only the current main branch is
maintained before a public release. Bind the development API and database to loopback.

Report vulnerabilities privately using GitHub's **Report a vulnerability** feature
when enabled. If unavailable, contact the project lead through a private channel
listed on their [GitHub profile](https://github.com/yassincodes404); do not post
exploit details publicly. A dedicated security contact and private-reporting setup
are release-blocking administrative tasks. No response-time promise is established yet.

Include affected revision, minimal reproduction, impact, and suggested mitigation.
Remove secrets and real customer observations. Do not run intrusive testing against
someone else's instance.

Genesis stores raw observations locally and uses no external model provider. Provider
credentials are not accepted or persisted yet. Remote adapters must introduce reviewed
secret handling, minimal payloads, redaction, safe errors, and controllable content
logging. Persisted credentials must be encrypted; environment references are preferred.
Database backups and access permissions are the operator's responsibility.

Dependency and artifact checks run in CI. Reported vulnerabilities must be evaluated
before public releases. Secrets, API keys, request content, and raw provider errors
must never appear in routine logs or CI artifacts.
