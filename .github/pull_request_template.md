## Description

<!-- Provide a brief description of the changes in this PR -->

## Type of Change

<!-- Mark the relevant option with an 'x' -->

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Code refactoring
- [ ] Other (please describe):

## Checklist

<!-- Mark completed items with an 'x'. All items should be checked before requesting review. -->

### Pre-Submission Checklist

- [ ] **Ansible Inclusion Checklist Compliance**
  - [ ] Ran `python scripts/check_inclusion_checklist.py --strict` and all checks passed
  - [ ] Reviewed `ANSIBLE_INCLUSION_CHECKLIST.md` for compliance
  - [ ] All module references in DOCUMENTATION use `M()` with FQCN (e.g., `M(graphiant.naas.graphiant_global_config)`)
  - [ ] All builtin modules use FQCN (e.g., `ansible.builtin.debug`)
  - [ ] Semantic markup is correct (V() for values, O() for options, etc.)

- [ ] **Code Quality**
  - [ ] Collection structure validation passed: `python scripts/validate_collection.py`
  - [ ] All linting checks pass locally
  - [ ] Code follows project style guidelines
  - [ ] No new linting errors introduced

- [ ] **Testing**
  - [ ] Local tests pass
  - [ ] Added/updated unit tests if applicable
  - [ ] E2E integration test passes (if applicable)

- [ ] **Documentation**
  - [ ] Updated README.md if needed
  - [ ] Updated module documentation if needed
  - [ ] Added/updated examples if applicable
  - [ ] Changelog updated (in `changelogs/changelog.yaml`) for user-facing changes

- [ ] **CI/CD**
  - [ ] All CI/CD workflows are expected to pass
  - [ ] No breaking changes to existing functionality (unless intentional)

## Testing

<!-- Describe the testing you performed to verify your changes -->

## Related Issues

<!-- Link to related issues using #issue_number -->

Fixes #
Related to #

## Additional Notes

<!-- Any additional information that reviewers should know -->

---

**Note:** This PR template helps ensure compliance with the [Ansible Inclusion Checklist](ANSIBLE_INCLUSION_CHECKLIST.md). Please review the checklist before submitting your PR.
