# Security Policy

## Supported Versions

We actively support security updates for the following versions of Transcript Create:

| Version | Supported          |
| ------- | ------------------ |
| latest (main) | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of Transcript Create seriously. If you have discovered a security vulnerability, we appreciate your help in disclosing it to us in a responsible manner.

### Where to Report

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via one of the following methods:

1. **GitHub Security Advisories** (Preferred): [Report a vulnerability](https://github.com/subculture-collective/transcript-create/security/advisories/new)
2. **Email**: security@subculture.community

### What to Include

Please include as much of the following information as possible:

- Type of vulnerability (e.g., SQL injection, XSS, authentication bypass)
- Full paths of source file(s) related to the manifestation of the vulnerability
- The location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

### Response Timeline

- **Initial Response**: We will acknowledge receipt of your vulnerability report within 48 hours
- **Status Update**: We will send a more detailed response within 7 days indicating the next steps
- **Fix Timeline**: We aim to release a fix within 30 days for HIGH/CRITICAL vulnerabilities
- **Disclosure**: We will coordinate with you on the disclosure timeline

### Security Update Policy

- **CRITICAL**: Immediate patch release within 24-48 hours
- **HIGH**: Patch release within 7 days
- **MEDIUM**: Included in next scheduled release (typically within 30 days)
- **LOW**: Evaluated for inclusion in future releases

## Security Scanning

This project implements multiple layers of security scanning:

### Automated Scans

1. **Dependency Scanning**
   - Python: `pip-audit` checks for known CVEs in dependencies
   - JavaScript: `npm audit` scans frontend dependencies
   - Schedule: On every PR, push to main/develop, and weekly

2. **Container Image Scanning**
   - Tool: Trivy
   - Scans Docker images for OS and package vulnerabilities
   - Results uploaded to GitHub Security tab
   - Schedule: On every Docker image build

3. **Secret Scanning**
   - Tool: Gitleaks
   - Detects API keys, tokens, passwords, and private keys
   - Runs in CI and as pre-commit hook
   - Schedule: On every commit and PR

4. **Static Application Security Testing (SAST)**
   - Tool: Bandit (Python)
   - Detects security issues like SQL injection, hardcoded secrets, insecure crypto
   - Schedule: On every PR and push to main/develop

### Security Features

- **Parameterized Database Queries**: All SQL queries use parameterized statements via SQLAlchemy
- **Authentication**: Optional OAuth 2.0 integration with secure token handling<sup>†</sup>
- **Rate Limiting**: API endpoints protected with rate limiting
- **Input Validation**: Pydantic models for request/response validation
- **Secret Management**: Environment variables for sensitive configuration

<sup>†</sup> OAuth 2.0 authentication is an optional feature. It requires installing additional dependencies and configuring the application. See the documentation for details on enabling OAuth support.
## Security Best Practices

When contributing to this project:

1. **Never commit secrets**: Use environment variables for sensitive data
2. **Use parameterized queries**: Always use SQLAlchemy ORM or parameterized text() queries
3. **Validate inputs**: Use Pydantic models for all API inputs
4. **Update dependencies**: Keep dependencies up to date
5. **Run pre-commit hooks**: Install and use the provided pre-commit hooks
6. **Review security warnings**: Address any security warnings in CI

## Vulnerability Disclosure Process

1. Security researcher reports vulnerability privately
2. We acknowledge and begin investigation
3. We develop and test a fix
4. We coordinate disclosure timeline with reporter
5. We release a security patch
6. We publish a security advisory
7. We credit the reporter (if desired)

## Security Contacts

- **Security Email**: security@subculture.community
- **GitHub Security**: Use [GitHub Security Advisories](https://github.com/subculture-collective/transcript-create/security/advisories)

## Recognition

We appreciate the security research community and recognize responsible disclosure. Security researchers who report valid vulnerabilities will be:

- Credited in the security advisory (with permission)
- Listed in our Hall of Fame (coming soon)
- Eligible for our bug bounty program (when launched)

## Additional Resources

- [GitHub Security Documentation](https://docs.github.com/en/code-security)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)

---

*Last Updated: 2025-10-28*
