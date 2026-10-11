# Security policy

## Reporting a vulnerability

Report suspected vulnerabilities through [GitHub private vulnerability reporting](https://github.com/caiolombello/vozena/security/advisories/new). Please do not disclose vulnerability details in a public issue, discussion, pull request, log, or recording.

Include the affected version, Fedora and PipeWire versions, reproduction steps, expected and observed behavior, and the security impact. Remove audio, credentials, usernames, private paths, meeting information, and unrelated device metadata unless a specific detail is essential to reproduce the problem.

Ordinary bugs and feature requests can use the [public issue tracker](https://github.com/caiolombello/vozena/issues).

## Supported versions

Security fixes target the latest published release. This first public preview is validated only on the environment described in [README.md](README.md); reports involving other environments are still welcome, but may require additional reproduction evidence.

## Security boundaries

Vozena runs as the current desktop user and processes microphone audio locally through PipeWire. It does not provide an account, network server, cloud processing, or telemetry service. Its optional 10-second voice sample stays in process memory and is removed when discarded or when the app closes.

The source release contains no third-party binary dependencies. `scripts/prepare.py` downloads pinned upstream archives and Python wheels over HTTPS, verifies fixed SHA-256 hashes, and installs them under user-owned local data directories. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for their origins and licenses.
