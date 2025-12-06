# Security Policy

## Supported Versions

We actively maintain security updates for the following versions of OneTask:

| Version | Supported          |
| ------- | ------------------ |
| 1.4.x   | :white_check_mark: |
| 1.3.x   | :white_check_mark: |
| < 1.3   | :x:                |

## Reporting a Vulnerability

We take the security of OneTask seriously. If you discover a security vulnerability, please follow these steps:

### For Critical Security Issues

**DO NOT** open a public issue for security vulnerabilities. Instead:

1. **Email**: Send details to [security contact email - replace with actual email]
2. **Subject**: Include "SECURITY" and a brief description
3. **Information to Include**:
   - Description of the vulnerability
   - Steps to reproduce the issue
   - Potential impact assessment
   - Any suggested fixes (optional)

### For Non-Critical Security Concerns

For general security questions or suggestions:
- Open a GitHub issue with the `security` label
- Use the security discussion board (if applicable)

## Response Timeline

- **Critical vulnerabilities**: Response within 24 hours
- **High severity**: Response within 72 hours  
- **Medium/Low severity**: Response within 1 week

## Security Measures

### Automated Security

OneTask employs several automated security measures:

- **Dependabot**: Automatic dependency vulnerability scanning and updates
- **Secret Scanning**: Detection of committed secrets and credentials
- **Push Protection**: Prevention of secret commits to the repository

### Manual Security Reviews

- Security validation checklist for all releases
- Regular dependency audits
- Periodic security code reviews
- Manual penetration testing for major releases

## Vulnerability Disclosure Process

1. **Receipt**: We acknowledge receipt of your report within 24 hours
2. **Assessment**: We assess the vulnerability and determine severity
3. **Development**: We develop and test a fix
4. **Release**: We prepare a security release
5. **Disclosure**: We publicly disclose the issue after the fix is released

## Security Best Practices for Users

### Deployment Security

- **Environment Variables**: Store secrets in environment variables, never in code
- **HTTPS**: Always use HTTPS in production deployments
- **Updates**: Keep OneTask and its dependencies updated
- **TaskWarrior**: Ensure TaskWarrior installation is current and secure

### Configuration Security

- **Debug Mode**: Disable Flask debug mode in production
- **Secret Key**: Use a strong, unique SECRET_KEY for Flask sessions
- **File Permissions**: Restrict access to TaskWarrior data directories
- **Network Access**: Limit network access to required ports only

### Data Protection

- **Backups**: Regularly backup TaskWarrior data with appropriate access controls
- **Access Control**: Implement appropriate authentication for multi-user environments
- **Monitoring**: Monitor application logs for suspicious activity

## Known Security Considerations

### TaskWarrior Integration

- OneTask executes TaskWarrior commands via subprocess
- Input validation prevents command injection attacks
- Timeout protections prevent resource exhaustion
- Error handling prevents information disclosure

### Web Application Security

- Input sanitization for task data display
- CSRF protection for state-changing operations
- XSS prevention through proper output encoding
- Security headers implementation

## Security Documentation

For detailed security procedures, see:

- `security-checklist.md` - Manual security validation checklist
- `security-scan-review.md` - Process for reviewing automated security scans
- `security-remediation.md` - Step-by-step remediation procedures

## Security Updates

Security updates are released as patch versions and are clearly marked in release notes. Subscribe to:

- GitHub repository releases for notifications
- Security advisories through GitHub's security tab

## Acknowledgments

We appreciate the security research community and will acknowledge security researchers who responsibly disclose vulnerabilities (with their permission).

## Questions?

If you have questions about this security policy or OneTask's security measures, please contact [contact information - replace with actual details].

---

**Last Updated**: 2025-12-06  
**Policy Version**: 1.0