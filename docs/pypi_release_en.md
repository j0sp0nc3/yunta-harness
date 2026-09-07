# PyPI Publishing & Distribution Guide — yunta-harness

This document details the steps to build, validate, and publish **Yunta** to the official Python Package Index ([PyPI](https://pypi.org/project/yunta-harness/)).

---

## 1. Package Identity on PyPI

- **PyPI Package Name**: `yunta-harness`  
  *(The name `yunta` was previously registered by an unrelated bioinformatics library; `yunta-harness` matches the official GitHub repository `github.com/j0sp0nc3/yunta-harness` 1:1).*
- **CLI Terminal Command**: `yunta`  
  *(Users who install the package get the `yunta` command in their shell).*
- **Python Import**: `from yunta import Agent, LiteLLMProvider, Usage`

---

## 2. Automated Publishing via GitHub Actions (Recommended)

The repository includes [`.github/workflows/publish.yml`](../.github/workflows/publish.yml), automating packaging and publishing upon every release.

### Option A: PyPI Trusted Publishing (OIDC — No secrets needed)
1. On [PyPI](https://pypi.org/manage/account/):
   - Navigate to **Publishing** and add a **Trusted Publisher**.
   - GitHub Owner: `j0sp0nc3`
   - Repository: `yunta-harness`
   - Workflow name: `publish.yml`
2. In GitHub, create a new **Release**:
   - Tag: `v1.0.2` (or current version).
   - Once published, GitHub Actions will build and deploy the package to PyPI automatically.

### Option B: Using Secret `PYPI_API_TOKEN`
1. Generate an API Token on PyPI (scoped to `yunta-harness`).
2. In your GitHub repository, go to **Settings > Secrets and variables > Actions**.
3. Create a secret named `PYPI_API_TOKEN` containing your token.
4. Trigger the workflow by publishing a GitHub Release or via **Actions > Publish to PyPI > Run workflow**.

---

## 3. Manual Local Publishing (Alternative)

If you prefer building and uploading directly from your local terminal:

### Step 1: Install build tools
```bash
pip install --upgrade build twine
```

### Step 2: Build distribution artifacts
```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build wheel (.whl) and source archive (.tar.gz)
python -m build
```

### Step 3: Validate package metadata
```bash
twine check dist/*
```
*(Should return `PASSED` with no errors).*

### Step 4: Upload to PyPI
```bash
# Upload to production PyPI
twine upload dist/*

# Or test first on TestPyPI:
twine upload --repository testpypi dist/*
```
Provide username `__token__` and password as your PyPI API token (`pypi-...`).

---

## 4. Verification

Once published, verify the installation in a clean virtual environment:

```bash
# Create a clean virtualenv
python -m venv test_env
source test_env/bin/activate  # On Windows: test_env\Scripts\activate

# 1. Install from PyPI
pip install yunta-harness

# 2. Verify terminal command
yunta

# 3. Verify Python library import
python -c "from yunta import Agent, LiteLLMProvider, Usage; print('Yunta imported successfully!')"
```
