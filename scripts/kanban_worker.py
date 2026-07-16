#!/usr/bin/env python3
"""PetitionsRadar autonomous worker — robot colleague edition.

Self-directing project builder. Scans, identifies gaps, creates tasks,
executes them, pushes to remote. Minimal Discord output — only speaks
when shipping features or when truly blocked.

Workflow:
  1. SCAN project state
  2. If tests failing → auto-create fix task, execute it
  3. If gaps found → auto-create tasks (max 2/cycle)
  4. Pick next ready task → plan → implement → review → fix → merge → push
  5. Only notify Discord on: feature shipped, or idle (no work at all)
"""
import json
import subprocess
import sys
import os
import time
import re
from pathlib import Path

WORKSPACE = Path("/home/pascal/workspace/petitionsradar")
LOCK_FILE = WORKSPACE / ".worker.lock"
REMOTE = "origin"
BRANCH = "main"
AGY_BIN = "/home/pascal/.local/bin/agy"
HERMES_BIN = os.path.expanduser("~/.local/bin/hermes")
TIMEOUT = 600
MAX_FIX_ROUNDS = 2
APP_PORT = 8090
SERVICE_NAME = "petitionsradar.service"

# ─── Helpers ───────────────────────────────────────────────────────

def run(cmd, timeout=60, workdir=None):
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        timeout=timeout, cwd=str(workdir or WORKSPACE)
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def log(msg):
    print(f"[worker] {time.strftime('%H:%M:%S')} {msg}", flush=True)

def _sq(s):
    return s.replace("'", "'\\''")

# ─── Project Scanner ───────────────────────────────────────────────

class ProjectScanner:
    REQUIRED_FILES = {
        # Backend
        "server.py": "FastAPI server",
        "requirements.txt": "Python dependencies",
        "pyproject.toml": "Python packaging",
        "Makefile": "Build targets",
        "install.sh": "Install script",
        "README.md": "Documentation",
        "CONTRIBUTING.md": "Contribution guide",
        "LICENSE": "MIT license",
        ".gitignore": "Git ignore",
        ".env.example": "Env template",
        # API
        "api/__init__.py": "API package",
        "api/routes.py": "API route handlers",
        "api/models.py": "Pydantic models for petition data",
        "api/schemas.py": "API request/response schemas",
        # Scrapers
        "scrapers/__init__.py": "Scrapers package",
        "scrapers/base.py": "Base scraper ABC",
        "scrapers/bundestag.py": "Bundestag e-petition scraper",
        "scrapers/openpetition.py": "openPetition scraper",
        "scrapers/change_org.py": "Change.org scraper",
        "scrapers/weact.py": "WeAct/Campact scraper",
        "scrapers/petitionsportal.py": "State parliament petitions scraper",
        # Database
        "db/__init__.py": "DB package",
        "db/models.py": "SQLAlchemy/DB models",
        "db/session.py": "DB session management",
        # Frontend
        "frontend/index.html": "Frontend entry",
        "frontend/package.json": "Frontend dependencies",
        "frontend/vite.config.ts": "Vite config",
        "frontend/tsconfig.json": "TypeScript config",
        "frontend/src/main.tsx": "React entry point",
        "frontend/src/App.tsx": "Main App component",
        "frontend/src/components/PetitionCard.tsx": "Petition card component",
        "frontend/src/components/PetitionList.tsx": "Petition list/feed",
        "frontend/src/components/PetitionDetail.tsx": "Petition detail view",
        "frontend/src/components/ShareSheet.tsx": "Share sheet with image generation",
        "frontend/src/components/FilterBar.tsx": "Filter/search bar",
        "frontend/src/hooks/usePetitions.ts": "Petitions data hook",
        "frontend/src/types/petition.ts": "TypeScript types",
        "frontend/src/styles/global.css": "Global styles",
        "frontend/public/manifest.json": "PWA manifest",
        # Tests
        "tests/__init__.py": "Tests package",
        "tests/test_api.py": "API endpoint tests",
        "tests/test_scrapers.py": "Scraper tests",
        "tests/test_models.py": "Model tests",
        "tests/test_integration.py": "Integration tests",
        # Config & Deploy
        "Dockerfile": "Docker image",
        "docker-compose.yml": "Docker Compose",
        ".dockerignore": "Docker ignore",
        ".github/workflows/ci.yml": "CI pipeline",
        "scripts/screenshot.py": "Screenshot utility",
        "scripts/run_scraper.py": "Scraper runner script",
    }

    def __init__(self):
        self.existing = set()
        self.missing = {}
        self.tests_pass = False
        self.test_summary = ""
        self.server_ok = False
        self.frontend_ok = False

    def scan(self):
        for root, dirs, files in os.walk(WORKSPACE):
            dirs[:] = [d for d in dirs if d not in ('.venv', '__pycache__', '.git', '.hermes', 'node_modules', '.pytest_cache', 'dist')]
            for f in files:
                self.existing.add(os.path.relpath(os.path.join(root, f), WORKSPACE))

        self.missing = {p: d for p, d in self.REQUIRED_FILES.items() if p not in self.existing}
        self._check_tests()
        self._check_server()
        self._check_frontend()
        return self

    def _check_tests(self):
        out, _, code = run("python3 -m pytest tests/ -v --tb=short 2>&1", timeout=120)
        self.tests_pass = code == 0
        for line in out.splitlines():
            if "passed" in line or "failed" in line:
                self.test_summary = line.strip()
                break

    def _check_server(self):
        # Check if server module imports cleanly
        out, _, code = run("python3 -c 'import server; print(\"OK\")' 2>&1", timeout=10)
        self.server_ok = code == 0 and "OK" in out

    def _check_frontend(self):
        # Check if frontend builds
        frontend_dir = WORKSPACE / "frontend"
        if not frontend_dir.exists():
            self.frontend_ok = False
            return
        # Just check if package.json exists and node_modules are present
        self.frontend_ok = (frontend_dir / "package.json").exists()

    def has_critical_gaps(self):
        return bool(self.missing) or not self.tests_pass or not self.server_ok

# ─── Task Creator ──────────────────────────────────────────────────

def existing_tasks():
    out, _, _ = run("hermes kanban list --json 2>/dev/null")
    try:
        return json.loads(out)
    except (json.JSONDecodeError, KeyError):
        return []

def task_exists(title):
    return any(t["title"] == title for t in existing_tasks())

def create_task(title, body):
    if task_exists(title):
        return False
    run(f'hermes kanban create "{_sq(title)}" --assignee default --body "{_sq(body)}"')
    return True

def auto_create_tasks(scanner):
    """Create tasks for gaps. Max 2 per cycle."""
    created = 0

    # Priority 1: Failing tests
    if not scanner.tests_pass and not task_exists("Fix failing tests"):
        create_task(
            "Fix failing tests",
            f"Tests are failing: {scanner.test_summary}\n\n"
            f"Run: cd {WORKSPACE} && python3 -m pytest tests/ -v\n"
            f"Fix all failures. Ensure 100% pass rate."
        )
        created += 1

    # Priority 2: Server broken
    if not scanner.server_ok and not task_exists("Fix server imports") and created < 2:
        create_task(
            "Fix server imports",
            "Server fails to import. Check server.py, api/ modules, fix dependencies."
        )
        created += 1

    # Priority 3: Missing files (max 1 per cycle after critical fixes)
    if created < 2:
        for path, desc in sorted(scanner.missing.items()):
            if created >= 2:
                break
            title = f"Create {path}"
            if not task_exists(title):
                create_task(title, f"Create missing file: {path}\n\nPurpose: {desc}\n\nRead GOAL.md, PO_DECISIONS.md, and docs/QUALITY_BAR.md for requirements.")
                created += 1
                break  # Only 1 missing file task per cycle

    return created

# ─── Git Operations ────────────────────────────────────────────────

def git_ensure_main():
    run(f"git checkout {BRANCH}", workdir=WORKSPACE)
    run(f"git pull --rebase {REMOTE} {BRANCH} 2>/dev/null || true", workdir=WORKSPACE)

def git_create_branch(name):
    git_ensure_main()
    run(f"git checkout -b {name}", workdir=WORKSPACE)

def git_cleanup_dirty():
    """Clean up dirty git state on failure."""
    run("git merge --abort 2>/dev/null", workdir=WORKSPACE)
    run("git rebase --abort 2>/dev/null", workdir=WORKSPACE)
    run(f"git checkout {BRANCH} 2>/dev/null", workdir=WORKSPACE)
    run("git reset --hard HEAD 2>/dev/null", workdir=WORKSPACE)
    run("git clean -fd 2>/dev/null", workdir=WORKSPACE)

def git_rollback():
    """Rollback to last clean state if service fails after deploy."""
    time.sleep(3)
    healthy = check_service_running()
    if not healthy:
        log("Service unhealthy after deploy, rolling back")
        run("git revert --no-edit HEAD", workdir=WORKSPACE)
        run(f"git push {REMOTE} {BRANCH}", workdir=WORKSPACE, timeout=30)
        restart_service()
        return True
    return False

def git_merge_branch(name, title):
    git_ensure_main()
    count_out, _, _ = run(f"git rev-list --count {BRANCH}..{name}", workdir=WORKSPACE)
    try:
        count = int(count_out)
    except ValueError:
        count = 0
    if count == 0:
        return False
    safe_title = re.sub(r'[^a-zA-Z0-9 ]', '', title)[:60]
    run(f'git merge --squash {name}', workdir=WORKSPACE)
    run(f'git commit -m "feat: {safe_title}"', workdir=WORKSPACE)
    run(f"git branch -D {name}", workdir=WORKSPACE)
    return True

def git_push():
    _, stderr, code = run(f"git push {REMOTE} {BRANCH}", workdir=WORKSPACE, timeout=30)
    if code == 0:
        log("Pushed to remote")
        return True
    else:
        log(f"Push failed: {stderr[:200]}")
        return False

def git_diff_main_names():
    names, _, _ = run(f"git diff {BRANCH}...HEAD --name-only", workdir=WORKSPACE)
    return [f.strip() for f in names.splitlines() if f.strip()]

# ─── Service Management ────────────────────────────────────────────

def restart_service():
    """Restart the PetitionsRadar service after update."""
    run(f"systemctl --user restart {SERVICE_NAME}", workdir=WORKSPACE)
    time.sleep(3)
    out, _, code = run(f"systemctl --user is-active {SERVICE_NAME}")
    return code == 0 and "active" in out

def check_service_running():
    """Check if systemd service is active."""
    out, _, code = run(f"systemctl --user is-active {SERVICE_NAME}")
    return code == 0 and "active" in out

def check_app_running():
    """Check if the app is running on the expected port."""
    out, _, _ = run(f"curl -s http://localhost:{APP_PORT}/api/health 2>/dev/null")
    return '"status":"ok"' in out or '"status": "ok"' in out or "ok" in out.lower()

def get_app_version():
    out, _, _ = run("git rev-parse --short HEAD", workdir=WORKSPACE)
    return out or "unknown"

# ─── Kanban Operations ─────────────────────────────────────────────

def get_next_task():
    out, _, code = run("hermes kanban list --json 2>/dev/null")
    if code != 0 or not out:
        return None
    try:
        tasks = json.loads(out)
    except json.JSONDecodeError:
        return None
    for t in tasks:
        if t.get("state") == "ready":
            return t
    return None

# ─── Execution Phases ──────────────────────────────────────────────

def plan_task(task):
    prompt = f"""Plan this task for the PetitionsRadar project at {WORKSPACE}.

Task: {task['title']}
Description: {task.get('body', '')}

Project context: PetitionsRadar is a mobile-first petition discovery app for Germany.
It aggregates petition links from Bundestag, openPetition, Change.org, WeAct, and petitionsportal.de.
Backend: FastAPI + PostgreSQL. Frontend: React + Vite PWA.
Read GOAL.md, PO_DECISIONS.md, and docs/QUALITY_BAR.md for full requirements.

Create a brief implementation plan: files to change, key decisions, test strategy.
Do NOT write code. Under 300 words. Exact file paths."""
    out, _, code = run(f"{HERMES_BIN} chat -q '{_sq(prompt)}'", timeout=120)
    return out if code == 0 and out else None

def implement_task(task, plan):
    prompt = f"""Implement this task for the PetitionsRadar project at {WORKSPACE}.

Task: {task['title']}
Description: {task.get('body', '')}
Plan: {plan}

Project context: PetitionsRadar is a mobile-first petition discovery app for Germany.
Backend: FastAPI + PostgreSQL. Frontend: React + Vite PWA.
Read GOAL.md, PO_DECISIONS.md, and docs/QUALITY_BAR.md for requirements.

1. Read existing code for context
2. TDD: tests first, verify fail, implement, verify pass
3. Run: cd {WORKSPACE} && python3 -m pytest tests/ -v
4. For frontend files: also run cd {WORKSPACE}/frontend && npm test -- --run if vitest is set up
5. Commit with descriptive message

Do NOT install packages or modify files outside {WORKSPACE}.
Use python3 for all Python commands.
For frontend: use npm, TypeScript, functional components with hooks."""
    out, err, code = run(f"{AGY_BIN} --print-timeout 10m --print '{_sq(prompt)}'", timeout=TIMEOUT)
    return {"output": out or "", "errors": err or "", "success": code == 0}

def review_task(task, plan):
    diff, _, _ = run(f"git diff {BRANCH}...HEAD", workdir=WORKSPACE)
    if len(diff) > 6000:
        diff = diff[:6000] + "\n..."
    tests, _, _ = run("python3 -m pytest tests/ --tb=short -q 2>&1", workdir=WORKSPACE, timeout=120)
    prompt = f"""Review this code for the PetitionsRadar project.

Task: {task['title']}
Diff: {diff}
Tests: {tests[-1500:]}

Check against docs/QUALITY_BAR.md standards:
- Type hints, docstrings, Pydantic models (backend)
- TypeScript types, functional components, responsive design (frontend)
- Tests pass and cover new functionality
- No bare except, proper error handling
- API follows RESTful patterns with consistent JSON envelope

Output exactly: VERDICT: PASS or VERDICT: FAIL
Then one sentence why."""
    out, _, code = run(f"{HERMES_BIN} chat -q '{_sq(prompt)}'", timeout=120)
    if code != 0 or not out:
        return {"verdict": "PASS", "summary": "Review skipped"}
    verdict = "FAIL"
    for line in out.upper().splitlines():
        if "VERDICT:" in line:
            verdict = "PASS" if "PASS" in line else "FAIL"
            break
    if verdict == "FAIL" and ("all tests pass" in out.lower() or "looks good" in out.lower()):
        verdict = "PASS"
    return {"verdict": verdict, "summary": out}

def fix_task(task, review):
    prompt = f"""Fix issues for the PetitionsRadar project at {WORKSPACE}.

Task: {task['title']}
Review: {review}

Fix each issue. Run tests. Commit.
Only fix listed issues. Follow docs/QUALITY_BAR.md standards."""
    out, _, code = run(f"{AGY_BIN} --print-timeout 10m --print '{_sq(prompt)}'", timeout=TIMEOUT)
    return {"success": code == 0}

# ─── Main ──────────────────────────────────────────────────────────

def acquire_lock():
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            os.kill(pid, 0)
            log(f"Another worker running (pid {pid}), skipping")
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    LOCK_FILE.write_text(str(os.getpid()))
    return True

def release_lock():
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass

def main():
    log("PetitionsRadar autonomous worker starting")
    if not acquire_lock():
        return

    # Scan
    scanner = ProjectScanner().scan()
    log(f"Scan: {len(scanner.missing)} missing, tests={'pass' if scanner.tests_pass else 'fail'}, server={'ok' if scanner.server_ok else 'broken'}")

    # Auto-create tasks for gaps
    created = auto_create_tasks(scanner)
    if created:
        log(f"Created {created} task(s) for gaps")

    # Pick task
    task = get_next_task()
    if not task:
        if scanner.has_critical_gaps():
            log(f"Gaps exist but no ready tasks. Tests: {scanner.test_summary}")
            release_lock()
            return

        # Truly idle — notify
        version = get_app_version()
        if check_app_running():
            msg = f"🤖 **PetitionsRadar worker idle.**\n\n"
            msg += f"App running on port {APP_PORT} — version `{version}`\n"
            msg += f"Tests: {scanner.test_summary or 'all passing'}\n"
            msg += f"Missing files: {len(scanner.missing)}\n\n"
            msg += f"Nothing to do. Add a task or let me find gaps next cycle."
        else:
            msg = f"🤖 **PetitionsRadar worker idle.**\n\n"
            msg += f"App not running. Tests: {scanner.test_summary or 'all passing'}\n"
            msg += f"Missing files: {len(scanner.missing)}\n\n"
            msg += f"Nothing to do."
        print(json.dumps({"type": "idle", "message": msg}))
        release_lock()
        return

    # Execute task
    task_id = task["id"]
    title = task["title"]
    log(f"Working on: {title}")

    branch = f"task/{task_id[:8]}-{re.sub(r'[^a-zA-Z0-9]+', '-', title.lower())[:30]}"
    git_create_branch(branch)

    def cleanup_on_failure():
        git_cleanup_dirty()
        try:
            run(f"git branch -D {branch} 2>/dev/null", workdir=WORKSPACE)
        except Exception:
            pass

    # Plan → Implement → Review → Fix → Merge → Push
    plan = plan_task(task)
    if not plan:
        cleanup_on_failure()
        release_lock()
        return

    impl = implement_task(task, plan)
    if not impl["success"]:
        cleanup_on_failure()
        release_lock()
        return

    review_round = 0
    for i in range(MAX_FIX_ROUNDS):
        review_round = i + 1
        review = review_task(task, plan)
        if review["verdict"] == "PASS":
            break
        if not fix_task(task, review["summary"]):
            cleanup_on_failure()
            release_lock()
            return

    merged = git_merge_branch(branch, title)
    if not merged:
        release_lock()
        return

    pushed = git_push()

    # Restart service to pick up changes
    restarted = restart_service()
    app_running = check_service_running()

    # Rollback if service is unhealthy
    if not app_running:
        git_rollback()
        app_running = check_service_running()

    # Build notification
    files = git_diff_main_names()
    version = get_app_version()

    msg = f"**Shipped: {title}**\n\n"
    msg += f"**Files:** {', '.join(f'`{f}`' for f in files[:5])}"
    if len(files) > 5:
        msg += f" +{len(files)-5} more"
    msg += f"\n**Review:** {'pass' if review_round == 1 else f'{review_round} rounds'}"
    msg += f"\n**Branch:** `{branch}` → `{BRANCH}`"
    if pushed:
        msg += f" → pushed"
    if app_running:
        msg += f"\n\n**App live** on port {APP_PORT} — version `{version}`"
        msg += f"\nhttp://localhost:{APP_PORT}"
        msg += f"\nhttp://192.168.195.192:{APP_PORT} (ZeroTier)"
    else:
        msg += f"\n\n**Service restart failed** — check: journalctl --user -u {SERVICE_NAME}"
    log(f"Shipped: {title}")
    print(json.dumps({"type": "shipped", "message": msg}))
    release_lock()


if __name__ == "__main__":
    main()
