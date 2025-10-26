# Security Policy

## Overview

This document outlines security practices and policies for the transcript-create project.

## Reporting Security Vulnerabilities

If you discover a security vulnerability, please report it by emailing the maintainers directly rather than opening a public issue. This helps protect users while a fix is being developed.

**Do not disclose security vulnerabilities publicly until a fix is available.**

## Secrets Management

### Environment Variables

All secrets must be stored in environment variables, never hardcoded in source code:

- **Required Secrets**:
  - `SESSION_SECRET`: Generate with `openssl rand -hex 32`
  - `STRIPE_API_KEY`: Stripe API key (use test keys for development)
  - `STRIPE_WEBHOOK_SECRET`: Stripe webhook signing secret
  - `OAUTH_GOOGLE_CLIENT_SECRET`: Google OAuth client secret (if using Google auth)
  - `OAUTH_TWITCH_CLIENT_SECRET`: Twitch OAuth client secret (if using Twitch auth)

- **Optional Secrets**:
  - `HF_TOKEN`: Hugging Face token for speaker diarization
  - `OPENSEARCH_PASSWORD`: OpenSearch authentication password

### Setup Instructions

1. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

2. Generate a secure session secret:

   ```bash
   openssl rand -hex 32
   ```

3. Fill in your secrets in `.env` - this file is gitignored and will not be committed.

4. Never use default/example values in production deployments.

### Pre-commit Hooks

This repository uses pre-commit hooks to prevent accidental secret commits:

```bash
# Install pre-commit
pip install pre-commit

# Install the git hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

The hooks include:

- **Gitleaks**: Scans for secrets and sensitive data
- **detect-private-key**: Detects private keys
- Code quality checks (black, isort, flake8)

## Dependency Security

### Pinned Dependencies

All Python dependencies are pinned to specific versions in `requirements.txt` to ensure:

- Reproducible builds
- Protection against supply chain attacks
- Controlled updates with security review

Full dependency tree is captured in `constraints.txt`.

### Automated Scanning

GitHub Actions automatically scans dependencies for vulnerabilities:

- **pip-audit**: Checks PyPI packages against OSV vulnerability database
- **safety**: Checks against Safety DB for known security issues
- Runs on: pushes to main/develop, pull requests, and weekly schedule
- Fails CI on high/critical severity vulnerabilities

### Updating Dependencies

When updating dependencies:

1. Review the changelog and security advisories
2. Test thoroughly in development
3. Run security scans: `pip-audit -r requirements.txt`
4. Update both `requirements.txt` and `constraints.txt`

### ROCm/CUDA Dependencies

PyTorch and related GPU packages are installed separately in the Dockerfile to support different hardware configurations. See `Dockerfile` for details.

## GitHub Security Features

### Secret Scanning

Enable GitHub's secret scanning for this repository:

1. Go to Settings → Security → Code security and analysis
2. Enable "Secret scanning"
3. Enable "Push protection" to prevent secret commits

### Dependabot

Consider enabling Dependabot for automated dependency updates:

1. Go to Settings → Security → Code security and analysis
2. Enable "Dependabot alerts"
3. Enable "Dependabot security updates"

## Production Deployment Security

### Essential Security Measures

1. **Use HTTPS**: Always serve the application over HTTPS in production
2. **Secure Secrets**: Use proper secret management (AWS Secrets Manager, HashiCorp Vault, etc.)
3. **Database Security**: Use strong passwords, enable SSL connections
4. **Firewall Rules**: Restrict access to database and internal services
5. **Session Security**: Use secure, httpOnly, sameSite cookies
6. **CORS**: Configure `FRONTEND_ORIGIN` to your actual frontend domain
7. **Rate Limiting**: Implement rate limiting on API endpoints
8. **Regular Updates**: Keep dependencies and system packages updated

### OpenSearch Security

For production OpenSearch deployments:

- Enable security plugin
- Use strong admin password
- Configure TLS/SSL
- Set up proper access controls
- See: <https://opensearch.org/docs/latest/security/>

### Stripe Integration Security

- Use live keys (`sk_live_...`) only in production
- Validate webhook signatures using `STRIPE_WEBHOOK_SECRET`
- Use HTTPS endpoints for webhooks
- Test webhooks using Stripe CLI in development

## Docker Security

When deploying with Docker:

- Use specific image tags, not `latest`
- Scan images for vulnerabilities: `docker scan <image>`
- Run containers as non-root user where possible
- Keep base images updated
- Use multi-stage builds to minimize attack surface

## Database Security

- Use connection pooling with limits
- Enable SSL/TLS for database connections in production
- Use read-only database users where appropriate
- Regular backups with encryption
- Audit database access logs

## Incident Response

If a security incident occurs:

1. Immediately rotate affected credentials
2. Review access logs for suspicious activity
3. Assess scope of potential data exposure
4. Notify affected users if required
5. Document incident and response
6. Review and update security measures

## Security Checklist for Production

Before deploying to production, ensure:

- [ ] All secrets are properly managed (not in code)
- [ ] `SESSION_SECRET` is generated securely
- [ ] Database uses strong passwords and SSL
- [ ] HTTPS is enabled for all endpoints
- [ ] CORS is configured correctly
- [ ] Secret scanning is enabled in GitHub
- [ ] Dependabot alerts are enabled
- [ ] Pre-commit hooks are installed
- [ ] Security audit passes (`pip-audit`, `safety check`)
- [ ] Docker images are scanned for vulnerabilities
- [ ] Rate limiting is configured
- [ ] Monitoring and alerting are set up
- [ ] Backup and recovery procedures are documented
- [ ] Security headers are configured (CSP, HSTS, etc.)

## Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security.html)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [PostgreSQL Security](https://www.postgresql.org/docs/current/security.html)
- [Docker Security](https://docs.docker.com/engine/security/)

## License

This security policy is part of the transcript-create project.
