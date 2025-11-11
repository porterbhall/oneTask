# OneTask Versioning and Release Process

## Semantic Versioning (SemVer) Rules for OneTask

OneTask follows Semantic Versioning 2.0.0 (`MAJOR.MINOR.PATCH`) with the following project-specific rules:

### MAJOR Version (X.0.0)
Increment when making incompatible changes that break existing functionality:
- **TaskWarrior Integration Changes**: Breaking changes to TaskWarrior command usage or data format requirements
- **API Breaking Changes**: Modifications to Flask endpoints that change request/response format
- **Configuration Breaking Changes**: Changes requiring manual user intervention or reconfiguration
- **Python Version Requirements**: Dropping support for previously supported Python versions
- **Database Schema Changes**: If future versions introduce data storage that requires migration

### MINOR Version (X.Y.0)
Increment when adding functionality in a backwards-compatible manner:
- **New Features**: Adding new timer modes, task management features, or UI enhancements
- **TaskWarrior Report Support**: Adding support for new TaskWarrior reports or configurations
- **New API Endpoints**: Adding new Flask routes while maintaining existing ones
- **UI Improvements**: New interface elements, themes, or accessibility features
- **Performance Enhancements**: Significant performance improvements
- **Dependency Updates**: Major dependency updates that add new functionality

### PATCH Version (X.Y.Z)
Increment when making backwards-compatible bug fixes:
- **Bug Fixes**: Fixing timer functionality, task completion issues, or display problems
- **Security Patches**: Security-related fixes and updates
- **Minor Dependency Updates**: Patch-level security updates for dependencies
- **Documentation Fixes**: Corrections to documentation without functional changes
- **Error Handling Improvements**: Better error messages or timeout handling
- **CSS/UI Fixes**: Visual fixes that don't add new functionality

## Release-Ready State Criteria

A release is considered ready when ALL of the following criteria are met:

### Code Quality
- [ ] All tests pass (`python test_completion.py`)
- [ ] No critical security vulnerabilities in dependencies
- [ ] Code follows project conventions and style guidelines
- [ ] No TODO comments remain for release-blocking items

### Functionality
- [ ] Flask application starts successfully (`python app.py`)
- [ ] TaskWarrior integration works with sample tasks
- [ ] Timer functionality works correctly (start/pause/complete)
- [ ] Task navigation (previous/next) functions properly
- [ ] Error handling works for common failure scenarios

### Documentation
- [ ] CLAUDE.md reflects any new functionality or changes
- [ ] README.md is updated with new features or requirements
- [ ] Version-specific release notes are prepared

### Environment
- [ ] Works with specified Python version (3.12+)
- [ ] All dependencies in requirements.txt are current and secure
- [ ] No conflicting or deprecated package versions

## Pre-Release Validation Checklist

Complete this checklist before creating any release:

### 1. Code Validation
```bash
# Test basic functionality
python app.py &
curl http://localhost:5000/
pkill -f "python app.py"

# Run tests
python test_completion.py

# Check dependencies for security issues
pip check
pip list --outdated
```

### 2. TaskWarrior Integration Testing
```bash
# Verify TaskWarrior is working
task --version
task list

# Test export functionality
task export next
task export ready
```

### 3. Version Validation
- [ ] Version number follows SemVer rules
- [ ] CHANGELOG.md entry created (if CHANGELOG exists)
- [ ] Release notes prepared
- [ ] Version increment rationale documented

### 4. Environment Testing
```bash
# Test in clean environment
python3 -m venv test_env
source test_env/bin/activate
pip install -r requirements.txt
python app.py
deactivate
rm -rf test_env
```

## Git Tagging Process

### 1. Prepare Release
```bash
# Ensure working directory is clean
git status

# Ensure you're on main branch
git checkout main
git pull origin main
```

### 2. Create Version Tag
```bash
# Create annotated tag with version number
git tag -a v1.2.3 -m "Release version 1.2.3

- Feature: Description of major features
- Fix: Description of important fixes
- Chore: Dependency updates, etc."

# Verify tag was created
git tag -l -n
```

### 3. Push Tags
```bash
# Push tags to remote repository
git push origin v1.2.3

# Or push all tags
git push --tags
```

## GitHub Release Creation Process

### 1. Navigate to GitHub Releases
1. Go to repository on GitHub
2. Click "Releases" tab
3. Click "Create a new release"

### 2. Release Configuration
- **Tag version**: Select the created tag (v1.2.3)
- **Release title**: "OneTask v1.2.3"
- **Description**: Use this template:

```markdown
## What's New in v1.2.3

### ✨ New Features
- Feature description

### 🐛 Bug Fixes  
- Fix description

### 🔧 Improvements
- Improvement description

### 📋 Dependencies
- Dependency updates

## Installation

```bash
git clone https://github.com/username/oneTask.git
cd oneTask
pip install -r requirements.txt
python app.py
```

## Requirements
- Python 3.12+
- TaskWarrior installed and configured
- Flask 3.1.1+

## Upgrade Notes
- Any breaking changes or migration steps
```

### 3. Release Options
- [ ] **Set as the latest release** (for stable releases)
- [ ] **This is a pre-release** (for alpha/beta/rc versions)

## Rollback Procedure

### If Release Has Issues

#### 1. Immediate Response
```bash
# Create hotfix branch from previous stable version
git checkout v1.2.2
git checkout -b hotfix/v1.2.4

# Apply critical fixes
# ... make necessary changes ...

# Create emergency patch release
git add .
git commit -m "Hotfix: Critical issue description"
git tag -a v1.2.4 -m "Hotfix release v1.2.4"
git push origin hotfix/v1.2.4
git push origin v1.2.4
```

#### 2. GitHub Release Rollback
1. Edit the problematic release on GitHub
2. Check "This is a pre-release" to demote it
3. Create new release from hotfix tag
4. Mark new release as "latest release"

#### 3. Communication
- Update release notes with known issues
- Notify users via appropriate channels
- Document lessons learned for future releases

### If Rollback to Previous Version Needed
```bash
# Reset to previous stable tag
git checkout v1.2.2
git checkout -b rollback/v1.2.2-restore

# Create rollback release
git tag -a v1.2.5 -m "Rollback to stable state (v1.2.2 functionality)"
git push origin rollback/v1.2.2-restore
git push origin v1.2.5
```

## Version Release Checklist

### Before Release
- [ ] Pre-release validation checklist completed
- [ ] Version number determined using SemVer rules
- [ ] Release notes drafted
- [ ] All tests pass
- [ ] Documentation updated

### During Release
- [ ] Git tag created with proper annotation
- [ ] Tag pushed to remote repository
- [ ] GitHub release created with proper description
- [ ] Release marked as latest (if stable)

### After Release
- [ ] Release announcement (if applicable)
- [ ] Monitor for issues in first 24 hours
- [ ] Update any external documentation mentioning version numbers
- [ ] Plan next release cycle