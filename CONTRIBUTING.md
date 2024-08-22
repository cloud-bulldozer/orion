# Contributing to Orion

First off, thank you for considering contributing to our project! It's people like you who make our project better and more enjoyable to use. The following is a set of guidelines for contributing to our repository. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Submitting Pull Requests](#submitting-pull-requests)
- [Development Guidelines](#development-guidelines)
  - [Branching Model](#branching-model)
  - [Coding Standards](#coding-standards)
  - [Commit Messages](#commit-messages)
- [Issue Tracking](#issue-tracking)
- [License](#license)

## Code of Conduct

By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md). Please read it to understand the expected behavior.

## How Can I Contribute?

### Reporting Bugs

If you encounter a bug, please open an issue on GitHub. Include the following details:

- A clear and descriptive title.
- A description of the problem and steps to reproduce it.
- The expected outcome and what actually happened.
- Screenshots, if applicable.
- Any relevant logs or error messages.

### Suggesting Enhancements

We welcome suggestions for new features or improvements. When suggesting an enhancement:

- Check if the feature is already being discussed.
- Clearly describe the enhancement and its benefits.
- Provide use cases where this would be useful.

### Submitting Pull Requests

1. **Fork** the repository.
2. **Create a branch** for your feature (`git checkout -b feature/your-feature-name`).
3. **Commit** your changes (`git commit -m 'Add some feature'`).
4. **Push** to the branch (`git push origin feature/your-feature-name`).
5. **Open a Pull Request** and describe your changes.

### Testing your code changes

We have CI tests already in place to test code changes from a fork repository as well. Once github actions is enabled in your fork, please run the below commands 

1. Install [Github CLI](https://cli.github.com/) and authenticate using the below command.
```
vchalla@vchalla-thinkpadp1gen2:~/myforks/orion$ gh auth login
? What account do you want to log into? GitHub.com
? What is your preferred protocol for Git operations on this host? HTTPS
? Authenticate Git with your GitHub credentials? Yes
? How would you like to authenticate GitHub CLI? Paste an authentication token
Tip: you can generate a Personal Access Token here https://github.com/settings/tokens
The minimum required scopes are 'repo', 'read:org', 'workflow'.
? Paste your authentication token: ****************************************
- gh config set -h github.com git_protocol https
✓ Configured git protocol
✓ Logged in as vishnuchalla
```
2. Set your fork as default repo to work with. For example
```
vchalla@vchalla-thinkpadp1gen2:~/myforks/orion$ gh repo set-default vishnuchalla/orion
```
3. List your availble workflows to run.
```
vchalla@vchalla-thinkpadp1gen2:~/myforks/orion$ gh workflow list
NAME           STATE   ID       
Builders       active  111655972
CI tests       active  112772727
Image Push     active  112772728
Pylint         active  111655973
Execute tests  active  112772729
```
4. For example CI tests, we need an elasticsearch server as a runtime secret which can be configured using below command.
```
vchalla@vchalla-thinkpadp1gen2:~/myforks/orion$ gh secret set QE_ES_SERVER --body 'YOUR_ES_SERVER'
```
5. Now lets trigger CI tests using its ID with the below command. We should see github actions getting triggered instantly in the fork repo.
```
vchalla@vchalla-thinkpadp1gen2:~/myforks/orion$ gh workflow run 112772727
✓ Created workflow_dispatch event for ci-tests.yaml at main

To see runs for this workflow, try: gh run list --workflow=ci-tests.yaml
```
Please make sure your code changes are in the same branch as your action workflows are configured to.

Ensure that your code follows the project's coding standards and includes tests where appropriate.

## Development Guidelines

### Branching Model

We use a simplified [Gitflow](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow) branching model:

- `main`: The latest stable release.
- `develop`: The current development branch.
- Feature branches: For new features and bug fixes (`feature/your-feature-name`).
- Release branches: For preparing a new release (`release/v1.0.0`).

### Coding Standards

- Follow the coding style used in the project. This usually includes indentation, naming conventions, and commenting.
- Write clear and concise code.
- Keep the code DRY (Don't Repeat Yourself) and SOLID principles in mind.

### Commit Messages

Use the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) format:
- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation updates
- `style:` for code style changes (formatting, missing semi colons, etc.)
- `refactor:` for code restructuring without changing behavior
- `test:` for adding or updating tests
- `chore:` for maintenance tasks

Example:
```
feat: add user login functionality
```

## Issue Tracking

We use GitHub Issues to track bugs, enhancements, and other requests. Please follow these guidelines when creating an issue:

* **Search Existing Issues**: Before creating a new issue, please check if the issue already exists. If it does, you can add a comment to that issue instead of creating a duplicate.
* **Be Descriptive**: Provide as much information as possible to help us understand and resolve the issue. This includes:
  * Steps to reproduce the issue
  * Expected behavior
  * Actual behavior
  * Screenshots or logs, if applicable
* **Use Labels**: Apply relevant labels to help us categorize the issue (e.g., bug, enhancement, documentation, etc.).

## License

By contributing to this project, you agree that your contributions will be licensed under the project's existing [license](LICENSE). Please ensure that your contributions are compatible with this license.