# Security Policy

## Supported Versions

We actively support the following versions with security updates:

| Version | Supported          | Notes                    |
| ------- | ------------------ | ------------------------ |
| 25.12.x | :white_check_mark: | Current stable release    |
| 25.11.x | :white_check_mark: | Previous release         |
| 25.10.x | :white_check_mark: | Legacy release           |
| < 25.10 | :x:                | No longer supported      |

**Note:** We recommend always using the latest version to ensure you have the most recent security patches.

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability, please follow these steps:

### How to Report

1. **Do NOT** open a public GitHub issue for security vulnerabilities
2. Email security details to: **security@graphiant.com**
3. Include the following information:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if available)
   - Your contact information

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Resolution**: Depends on severity (see below)

### Severity Levels

| Severity | Response Time | Description                                    |
|----------|---------------|------------------------------------------------|
| Critical | 24-48 hours    | Remote code execution, authentication bypass   |
| High     | 7 days         | Privilege escalation, data exposure           |
| Medium   | 30 days        | Information disclosure, denial of service     |
| Low      | 90 days        | Best practice violations, minor issues         |

### What to Expect

- **Acknowledgment**: You will receive an acknowledgment email within 48 hours
- **Updates**: Regular updates on the status of the vulnerability
- **Credit**: With your permission, we will credit you in security advisories
- **Disclosure**: We will coordinate public disclosure after a fix is available

## Security Best Practices

### Credential Management

**Never commit credentials to the repository:**

- ❌ **Don't**: Hardcode passwords, API keys, or tokens in playbooks or modules
- ✅ **Do**: Use environment variables, Ansible Vault, or secure credential stores

```yaml
# ❌ BAD - Never do this
host: "https://api.graphiant.com"
username: "myuser"
password: "mypassword"

# ✅ GOOD - Use environment variables
host: "{{ lookup('env', 'GRAPHIANT_HOST') }}"
username: "{{ lookup('env', 'GRAPHIANT_USERNAME') }}"
password: "{{ lookup('env', 'GRAPHIANT_PASSWORD') }}"
```

**Best Practices:**
- Use GitHub Secrets/Variables for CI/CD credentials
- Use Ansible Vault for sensitive data in playbooks
- Rotate credentials regularly
- Use least-privilege access principles
- Never log or print credentials in output

### Code Security

**Secure Coding Practices:**

- ✅ Validate and sanitize all user inputs
- ✅ Use parameterized queries/API calls (prevent injection attacks)
- ✅ Implement proper error handling (don't expose sensitive information)
- ✅ Follow principle of least privilege
- ✅ Use secure defaults

**Example:**
```python
# ✅ GOOD - Input validation
def validate_host(host):
    if not host.startswith(('https://', 'http://')):
        raise ValueError("Host must start with http:// or https://")
    # Additional validation...
    return host
```

### Dependency Management

**Keep Dependencies Updated:**

- ✅ Regularly update `requirements.txt` dependencies
- ✅ Review and update Ansible collection dependencies in `galaxy.yml`
- ✅ Monitor for security advisories in dependencies
- ✅ Use dependency pinning for reproducible builds

**Check for Vulnerabilities:**
```bash
# Check Python dependencies
pip-audit -r requirements.txt

# Check Ansible collection dependencies
ansible-galaxy collection verify graphiant.naas
```

### CI/CD Security

**GitHub Actions Security:**

- ✅ Use GitHub Secrets for sensitive data (never hardcode)
- ✅ Use least-privilege permissions in workflows
- ✅ Enable branch protection rules
- ✅ Require signed commits (GPG signatures)
- ✅ Enable code scanning (CodeQL)
- ✅ Review workflow changes carefully

**Workflow Best Practices:**
- Use `secrets.GITHUB_TOKEN` with minimal required permissions
- Never echo or log secrets
- Use `continue-on-error` carefully (don't hide security failures)
- Validate artifacts before publishing

### Repository Security

**Access Control:**

- ✅ Use CODEOWNERS for required reviews
- ✅ Require SRE team approval for sensitive changes
- ✅ Use branch protection rules
- ✅ Enable required status checks
- ✅ Require signed commits

**Branch Protection:**
- Protected branches: `main`, `develop`
- Required approvals: SRE team and code owners
- Required status checks: All CI/CD workflows must pass
- Merge restrictions: No merge commits, signed commits only

### Ansible-Specific Security

**Playbook Security:**

- ✅ Use `check_mode` for testing (no actual changes)
- ✅ Use `--ask-vault-pass` or `--vault-password-file` for vault-encrypted files
- ✅ Validate playbook syntax before execution
- ✅ Use `no_log: true` for tasks with sensitive output

```yaml
# ✅ GOOD - Hide sensitive output
- name: Authenticate
  ansible.builtin.uri:
    url: "{{ api_url }}/auth/login"
    method: POST
    body_format: json
    body:
      username: "{{ username }}"
      password: "{{ password }}"
  no_log: true  # Prevents password from appearing in logs
  register: auth_result
```

**Module Security:**
- Validate all inputs before making API calls
- Handle errors gracefully without exposing sensitive data
- Use secure defaults
- Document security considerations in module documentation

### Environment Variables

**Secure Environment Variable Usage:**

```bash
# ✅ GOOD - Set in environment
export GRAPHIANT_HOST="https://api.graphiant.com"
export GRAPHIANT_USERNAME="your_username"
export GRAPHIANT_PASSWORD="your_password"

# ❌ BAD - Don't commit to .env files in repository
echo "GRAPHIANT_PASSWORD=mypassword" >> .env
```

### Testing Security

**Security Testing:**

- ✅ Run security linters (bandit, safety, etc.)
- ✅ Test with invalid inputs (fuzzing)
- ✅ Test authentication and authorization
- ✅ Review test coverage for security-critical paths

### Documentation Security

**Security Documentation:**

- ✅ Document security considerations in module docs
- ✅ Include security warnings for sensitive operations
- ✅ Document credential requirements clearly
- ✅ Provide secure usage examples

## Security Checklist for Contributors

Before submitting a pull request, ensure:

- [ ] No credentials or secrets are committed
- [ ] All inputs are validated
- [ ] Error messages don't expose sensitive information
- [ ] Dependencies are up to date
- [ ] Security-related code is documented
- [ ] Tests cover security-critical paths
- [ ] Commits are GPG signed
- [ ] Code passes security scans (CodeQL)

## Security Updates

Security updates are released as:
- **Patch releases** (e.g., 25.11.2 → 25.11.3) for security fixes
- **Security advisories** published on GitHub Security tab
- **Release notes** include security-related changes

## Additional Resources

- [GitHub Security Best Practices](https://docs.github.com/en/code-security)
- [Ansible Security Best Practices](https://docs.ansible.com/ansible/latest/user_guide/playbooks_best_practices.html#security-best-practices)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Graphiant Documentation](https://docs.graphiant.com)

## Contact

- **Security Issues**: security@graphiant.com
- **General Support**: support@graphiant.com
- **GitHub Issues**: [Create an issue](https://github.com/Graphiant-Inc/graphiant-playbooks/issues) (for non-security issues only)

---

**Last Updated**: 2025-12-22
