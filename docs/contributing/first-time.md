# First-Time Contributors Guide

Welcome! 🎉 This guide will walk you through making your first contribution to Transcript Create, step by step.

## Table of Contents

- [Before You Start](#before-you-start)
- [Finding Your First Issue](#finding-your-first-issue)
- [Setting Up Your Environment](#setting-up-your-environment)
- [Making Your Changes](#making-your-changes)
- [Submitting Your Contribution](#submitting-your-contribution)
- [After Submission](#after-submission)
- [Getting Help](#getting-help)
- [Next Steps](#next-steps)

## Before You Start

### What You'll Need

- **GitHub Account**: [Sign up](https://github.com/signup) if you don't have one
- **Git**: Version control system - [Installation guide](https://git-scm.com/downloads)
- **Basic Git Knowledge**: Understanding of commits, branches, and pull requests
  - New to Git? Try [GitHub's Git Guide](https://guides.github.com/introduction/git-handbook/)

### Understanding the Contribution Process

Here's the high-level flow:

```
1. Find an issue to work on
   ↓
2. Fork the repository
   ↓
3. Clone your fork locally
   ↓
4. Create a new branch
   ↓
5. Make your changes
   ↓
6. Test your changes
   ↓
7. Commit and push
   ↓
8. Create a pull request
   ↓
9. Address feedback
   ↓
10. Merge! 🎉
```

### Our Code of Conduct

Please read our [Code of Conduct](../../CODE_OF_CONDUCT.md). We're committed to providing a welcoming and inclusive environment for all contributors.

## Finding Your First Issue

### Good First Issues

We label beginner-friendly issues with `good first issue`. These are:
- Well-defined with clear acceptance criteria
- Relatively small in scope
- Have guidance and hints
- Don't require deep knowledge of the codebase

**Find them here**: [Good First Issues](https://github.com/subculture-collective/transcript-create/labels/good%20first%20issue)

### Types of First Contributions

Here are some great ways to start:

#### Documentation
- Fix typos or unclear wording
- Add examples or clarifications
- Improve setup instructions
- Write tutorials or guides

**Why start here**: No complex setup required, helps you understand the project

#### Tests
- Add missing test cases
- Improve test coverage
- Fix failing tests

**Why start here**: Learn the codebase, testing is always valuable

#### Bug Fixes
- Fix small bugs
- Handle edge cases
- Improve error messages

**Why start here**: Clear problem to solve, immediate impact

#### Small Features
- Add configuration options
- Implement helper functions
- Improve UI elements

**Why start here**: Build confidence with small, complete features

### Claiming an Issue

When you find an issue you want to work on:

1. **Read the issue carefully**
   - Understand the problem
   - Check acceptance criteria
   - Review any linked discussions

2. **Comment on the issue**
   ```
   Hi! I'd like to work on this issue. This would be my first contribution.
   
   My approach would be:
   1. [Step 1]
   2. [Step 2]
   
   Does this sound good?
   ```

3. **Wait for confirmation**
   - A maintainer will respond (usually within 48 hours)
   - They may provide guidance or suggestions
   - Once confirmed, you can start working!

**Pro Tip**: Don't work on multiple first issues at once. Focus on completing one first.

## Setting Up Your Environment

### 1. Fork the Repository

On the [Transcript Create repository page](https://github.com/subculture-collective/transcript-create):

1. Click the "Fork" button in the top-right corner
2. This creates a copy under your GitHub account
3. You'll be redirected to your fork

### 2. Clone Your Fork

```bash
# Replace YOUR_USERNAME with your GitHub username
git clone https://github.com/YOUR_USERNAME/transcript-create.git

# Navigate into the directory
cd transcript-create

# Add the original repo as "upstream" (to sync later)
git remote add upstream https://github.com/subculture-collective/transcript-create.git

# Verify remotes
git remote -v
# Should show:
# origin    https://github.com/YOUR_USERNAME/transcript-create.git (fetch)
# origin    https://github.com/YOUR_USERNAME/transcript-create.git (push)
# upstream  https://github.com/subculture-collective/transcript-create.git (fetch)
# upstream  https://github.com/subculture-collective/transcript-create.git (push)
```

### 3. Install Dependencies

#### For Documentation Changes

No installation needed! Just a text editor.

#### For Code Changes

Follow the [Development Setup Guide](../development/setup.md). Quick start:

```bash
# Option 1: Docker Compose (Recommended for beginners)
cp .env.example .env
# Edit .env and set SESSION_SECRET (see setup guide)
docker compose build
docker compose up -d

# Option 2: Local Development (Faster iteration)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. Install Pre-commit Hooks

These ensure code quality before committing:

```bash
# Quick setup
./scripts/setup_precommit.sh

# Or manually
pip install pre-commit
pre-commit install
```

## Making Your Changes

### 1. Create a New Branch

Always create a new branch for your changes:

```bash
# Update your main branch first
git checkout main
git pull upstream main

# Create and switch to a new branch
# Use descriptive names:
git checkout -b fix/typo-in-readme           # For bug fixes
git checkout -b feature/add-export-button    # For features
git checkout -b docs/improve-setup-guide     # For docs

# Verify you're on the new branch
git branch
# Should show * next to your branch name
```

### 2. Make Your Changes

Open the relevant files in your editor and make your changes.

**Tips**:
- Keep changes focused on the issue you're fixing
- Don't fix multiple unrelated things in one PR
- Follow existing code style
- Read nearby code to understand patterns

### 3. Test Your Changes

#### Documentation Changes

- Read through your changes
- Check for typos and formatting
- Verify links work

#### Code Changes

```bash
# Backend tests
pytest tests/

# Frontend tests
cd frontend
npm test

# Run linters
ruff check app/ worker/
black --check app/ worker/
```

See [Testing Guide](../development/testing.md) for details.

### 4. Commit Your Changes

```bash
# Stage your changes
git add .

# Or stage specific files
git add README.md docs/setup.md

# Commit with a clear message
git commit -m "docs: fix typo in installation instructions"

# Commit message format:
# <type>: <description>
#
# Types:
# - feat: New feature
# - fix: Bug fix
# - docs: Documentation changes
# - test: Adding or updating tests
# - refactor: Code refactoring
# - style: Formatting changes
# - chore: Maintenance tasks
```

**Good commit messages**:
```
docs: fix typo in setup guide
fix: correct YouTube URL validation regex
feat: add export to PDF button
test: add unit tests for video processing
```

**Bad commit messages**:
```
fixed stuff
update
changes
asdfasdf
```

## Submitting Your Contribution

### 1. Push Your Branch

```bash
# Push your branch to your fork
git push origin your-branch-name

# Example:
git push origin fix/typo-in-readme
```

### 2. Create a Pull Request

1. Go to your fork on GitHub
2. You'll see a banner: "Compare & pull request" - click it
3. Or: Go to the original repo → "Pull requests" → "New pull request" → "compare across forks"

### 3. Fill Out the PR Template

The template will guide you. Key sections:

**Title**: Clear and descriptive
```
Good: "Fix typo in installation instructions"
Bad: "Update README"
```

**Description**: Explain what and why
```markdown
## Description
Fixed a typo in the installation section where "pip install" was written as "pip instal".

## Related Issues
Fixes #123

## Type of Change
- [x] Documentation update

## Checklist
- [x] I have read the Code of Conduct
- [x] I have reviewed my changes
- [x] Documentation is updated
```

### 4. Wait for Review

- Maintainers will review your PR (usually within 2-3 days)
- They may request changes
- Don't be discouraged by feedback - it's part of the process!

## After Submission

### Responding to Feedback

When reviewers request changes:

1. **Read feedback carefully**
   - Understand what's being asked
   - Ask questions if unclear

2. **Make the requested changes**
   ```bash
   # Make changes in your branch
   git add .
   git commit -m "address review feedback: improve error handling"
   git push origin your-branch-name
   ```

3. **Reply to comments**
   - "Done ✅" for completed items
   - Explain your approach if you did something different
   - Ask questions if you're stuck

### Common Feedback Topics

**Code Style**
- "Please run black to format the code"
- "Add type hints to this function"
- Solution: Run formatters and linters

**Tests**
- "Can you add a test for this?"
- "This test isn't covering the edge case"
- Solution: Add or improve tests

**Documentation**
- "Please update the docstring"
- "Add a comment explaining this logic"
- Solution: Improve documentation

**Scope**
- "This PR is doing too many things"
- "Let's split this into separate PRs"
- Solution: Create focused PRs

### Your PR Gets Merged! 🎉

Congratulations! You're now a contributor to Transcript Create!

What happens next:
1. Your changes are merged to the main branch
2. You'll be added to the contributors list
3. Your changes will be included in the next release

## Getting Help

### Stuck on Something?

**Don't be shy about asking for help!** We're here to support you.

### Where to Ask

1. **On your PR**: Comment directly if it's about your PR
2. **On the issue**: Ask clarifying questions about the issue
3. **Create a new issue**: For general questions, use the [question template](https://github.com/subculture-collective/transcript-create/issues/new/choose)

### What to Include

When asking for help:
- What you're trying to do
- What you've tried
- What's not working (error messages, unexpected behavior)
- Your environment (OS, Python version, etc.)

**Good question**:
```
I'm trying to run the tests but getting this error:
[error message]

I've tried:
1. Reinstalling dependencies
2. Checking Python version (3.11)

My environment:
- OS: Ubuntu 22.04
- Python: 3.11.5

Any suggestions?
```

**Less helpful**:
```
Tests don't work. Help?
```

### Response Time

- We try to respond within 48 hours
- If you haven't heard back in 3-4 days, feel free to ping us

## Next Steps

### After Your First Contribution

1. **Celebrate!** You did it! 🎉
2. **Update your skills**: Add "Open Source Contributor" to your resume/LinkedIn
3. **Find another issue**: Now that you're familiar with the process, try a slightly more complex issue
4. **Help others**: Answer questions from other first-time contributors

### Growing as a Contributor

#### Build Your Skills

- Read the [Code Guidelines](../development/code-guidelines.md)
- Study the [Architecture](../development/architecture.md)
- Explore the codebase
- Review other people's PRs to learn

#### Take On More

- Move from `good first issue` to regular issues
- Work on features, not just bugs
- Review pull requests
- Help with documentation
- Answer questions in discussions

#### Become a Regular Contributor

- Make multiple contributions over time
- Build expertise in specific areas
- Help maintain the project
- Mentor new contributors

### Recognition

All contributors are recognized in [CONTRIBUTORS.md](../../CONTRIBUTORS.md). Your contributions, big or small, are valued!

## Common Pitfalls to Avoid

### 1. Working on the Wrong Branch
```bash
# Always work on a feature branch, not main
git checkout -b my-feature  # ✅ Correct
# Not: git checkout main      # ❌ Wrong
```

### 2. Forgetting to Sync with Upstream
```bash
# Before starting new work, sync with upstream
git checkout main
git pull upstream main
git checkout -b my-new-feature
```

### 3. Making Too Many Changes
- Keep PRs focused and small
- One issue per PR (unless issues are related)
- Split large changes into multiple PRs

### 4. Not Testing Changes
- Always test your changes locally
- Run the test suite
- Manually verify the fix works

### 5. Vague Commit Messages
```bash
# Good
git commit -m "fix: correct YouTube URL validation regex"

# Bad
git commit -m "fixed bug"
```

## Resources

### Documentation
- [Development Setup](../development/setup.md)
- [Architecture Overview](../development/architecture.md)
- [Code Guidelines](../development/code-guidelines.md)
- [Testing Guide](../development/testing.md)

### External Resources
- [GitHub Docs - Forking a Repo](https://docs.github.com/en/get-started/quickstart/fork-a-repo)
- [GitHub Docs - Creating a Pull Request](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request)
- [First Timers Only](https://www.firsttimersonly.com/)
- [How to Contribute to Open Source](https://opensource.guide/how-to-contribute/)

### Community
- [GitHub Discussions](https://github.com/subculture-collective/transcript-create/discussions)
- [Issues](https://github.com/subculture-collective/transcript-create/issues)

## Encouragement

Remember:
- **Everyone was a first-time contributor once** - including the project maintainers!
- **Mistakes are okay** - they're how we learn
- **Questions are welcome** - there are no stupid questions
- **Small contributions matter** - every PR, no matter how small, helps improve the project
- **Take your time** - quality over speed

You've got this! We're excited to see your contribution. 🚀

---

**Still have questions?** Feel free to:
- Comment on any issue
- Open a discussion
- Reach out to maintainers

Welcome to the Transcript Create community! 🎉
