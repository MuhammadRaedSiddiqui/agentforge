"""
Full environment cleanup for Agent Forge staging.

Deletes ALL existing resources across platforms:
  - Make.com:  all scenarios + all hooks for the configured team
  - Vapi:      all assistants (+ optionally tools)
  - Render:    service deploys are NOT deleted (Render has no bulk-delete);
               this step only reports and optionally suspends via API.

Safety:
  - Defaults to --dry-run (no deletes).
  - Requires --execute to actually delete.
  - Blocks when AGENT_FORGE_ENV == production unless --force-production.
  - Requires interactive "DELETE ALL" confirmation unless --yes.
  - Every delete is idempotent: 404 Already Deleted counts as success.
  - Rate-limited deletes with backoff on 429.

Usage:
  python scripts/cleanup_all.py                          # dry-run preview
  python scripts/cleanup_all.py --execute                # interactive confirm + delete
  python scripts/cleanup_all.py --execute --yes          # no prompt (CI)
  python scripts/cleanup_all.py --execute --only make    # only Make
  python scripts/cleanup_all.py --execute --skip vapi    # skip Vapi
  python scripts/cleanup_all.py --include-tools          # also delete Vapi tools
  python scripts/cleanup_all.py --force-production --execute --yes  # DANGER

Env (from .env):
  MAKE_API_TOKEN, MAKE_TEAM_ID, MAKE_ZONE
  VAPI_API_KEY
  AGENT_FORGE_ENV
  HOSTING_API_TOKEN, HOSTING_SERVICE_ID (optional, for Render status)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure repo root on sys.path for `adapters.*` imports when run as `python scripts/...`
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402  (needs REPO_ROOT on sys.path first)

from shared.console import enable_utf8_output  # noqa: E402  (needs REPO_ROOT on sys.path first)

load_dotenv(REPO_ROOT / ".env")

# Windows console: force UTF-8 so box-drawing / emoji don't raise cp1252 errors
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# ── Helpers ──────────────────────────────────────────────────────────────

RESET = "\033[0m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"


def c(text: str, color: str) -> str:
    if sys.stdout.isatty():
        return f"{color}{text}{RESET}"
    return text


def env_guard(force_production: bool) -> None:
    env = os.getenv("AGENT_FORGE_ENV", "staging")
    if env == "production" and not force_production:
        print(c("\n⛔  AGENT_FORGE_ENV=production — refusing to wipe.", RED + BOLD))
        print("   This script deletes ALL resources for the team/account.")
        print("   If you really mean it, re-run with --force-production --execute --yes\n")
        sys.exit(2)


def confirm_destructive(total: int, dry_run: bool) -> bool:
    if dry_run:
        return True
    print(c("\n⚠️  DESTRUCTIVE ACTION", YELLOW + BOLD))
    print(f"   This will permanently delete {total} remote resource(s) across all platforms.")
    print("   This cannot be undone. Make sure AGENT_FORGE_ENV=staging.")
    answer = input(c("\n   Type DELETE ALL to confirm, or anything else to abort: ", YELLOW))
    return answer.strip() == "DELETE ALL"


# ── Make.com ─────────────────────────────────────────────────────────────


def cleanup_make(dry_run: bool) -> dict[str, Any]:
    """List and optionally delete all Make scenarios + hooks for the team."""
    summary: dict[str, Any] = {
        "scenarios": [],
        "hooks": [],
        "deleted": 0,
        "failed": 0,
        "skipped": 0,
    }

    try:
        from adapters.make import MakeAdapter
    except Exception as e:
        print(c(f"  ✗ Make adapter import failed: {e}", RED))
        summary["error"] = str(e)
        return summary

    try:
        adapter = MakeAdapter()
    except Exception as e:
        print(c(f"  ✗ Make not configured: {e}", YELLOW))
        print("     Set MAKE_API_TOKEN + MAKE_TEAM_ID in .env to enable Make cleanup.")
        summary["error"] = str(e)
        return summary

    # — Scenarios —
    print(c("\n  Make — scenarios", BOLD))
    try:
        receipt = adapter.list_scenarios()
        scenarios = receipt.response_data.get("scenarios", [])
        print(
            f"    Found {len(scenarios)} scenario(s) for team {adapter.team_id} (zone {adapter.zone})"
        )
        for s in scenarios:
            sid = s.get("id")
            name = s.get("name", "?")
            active = s.get("isActive", s.get("is_active", "?"))
            print(f"      • [{sid}] {name}  active={active}")
            summary["scenarios"].append(s)

        if not dry_run:
            for s in scenarios:
                sid = int(s["id"])
                name = s.get("name", str(sid))
                try:
                    # Deactivate first if active — delete of active scenario can 409 on some zones
                    if s.get("isActive") is True:
                        try:
                            adapter.deactivate_scenario(sid)
                            print(c(f"      ○ Deactivated [{sid}] {name}", YELLOW))
                            time.sleep(0.35)
                        except Exception as de:
                            # Non-fatal: try delete anyway; log the deactivate error
                            print(c(f"      ! Deactivate failed [{sid}]: {de}", YELLOW))
                    adapter.delete_scenario(sid)
                    print(c(f"      ✓ Deleted scenario [{sid}] {name}", GREEN))
                    summary["deleted"] += 1
                    time.sleep(0.4)  # gentle rate limit
                except Exception as e:
                    msg = str(e)
                    if "404" in msg or "Not found" in msg:
                        print(c(f"      ○ Already gone [{sid}] {name}", YELLOW))
                        summary["deleted"] += 1
                    elif "429" in msg:
                        print(c(f"      ! Rate limited [{sid}], backing off 3s…", YELLOW))
                        time.sleep(3)
                        try:
                            adapter.delete_scenario(sid)
                            print(c(f"      ✓ Deleted on retry [{sid}] {name}", GREEN))
                            summary["deleted"] += 1
                        except Exception as e2:
                            print(c(f"      ✗ Failed [{sid}] {name}: {e2}", RED))
                            summary["failed"] += 1
                    else:
                        print(c(f"      ✗ Failed [{sid}] {name}: {e}", RED))
                        summary["failed"] += 1
        else:
            print(c("    (dry-run — no deletes)", CYAN))
            summary["skipped"] = len(scenarios)

    except Exception as e:
        print(c(f"    ✗ list/delete scenarios failed: {e}", RED))
        summary["error"] = str(e)

    # — Hooks —
    print(c("\n  Make — hooks", BOLD))
    try:
        receipt = adapter.list_hooks()
        hooks = receipt.response_data.get("hooks", [])
        print(f"    Found {len(hooks)} hook(s)")
        for h in hooks:
            hid = h.get("id")
            name = h.get("name", "?")
            tname = h.get("typeName", h.get("type_name", "?"))
            print(f"      • [{hid}] {name}  type={tname}")
            summary["hooks"].append(h)

        if not dry_run:
            for h in hooks:
                hid = int(h["id"])
                name = h.get("name", str(hid))
                try:
                    adapter.delete_hook(hid, confirmed=True)
                    print(c(f"      ✓ Deleted hook [{hid}] {name}", GREEN))
                    summary["deleted"] += 1
                    time.sleep(0.35)
                except Exception as e:
                    msg = str(e)
                    if "404" in msg or "Not found" in msg:
                        print(c(f"      ○ Already gone hook [{hid}] {name}", YELLOW))
                        summary["deleted"] += 1
                    else:
                        print(c(f"      ✗ Failed hook [{hid}] {name}: {e}", RED))
                        summary["failed"] += 1
        else:
            print(c("    (dry-run — no deletes)", CYAN))
            summary["skipped"] += len(hooks)
    except Exception as e:
        print(c(f"    ✗ list/delete hooks failed: {e}", RED))
        summary["hooks_error"] = str(e)

    return summary


# ── Vapi ─────────────────────────────────────────────────────────────────


def _vapi_request(method: str, path: str, api_key: str, json_data: dict | None = None) -> Any:
    """Raw Vapi request helper (used for list which the adapter lacks)."""
    import requests

    url = f"https://api.vapi.ai{path}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.request(method, url, headers=headers, json=json_data, timeout=(10, 30))
    # Map to typed errors similar to adapter for uniform handling
    if resp.status_code in (401, 403):
        raise PermissionError(f"HTTP {resp.status_code}: Unauthorized — check VAPI_API_KEY")
    if resp.status_code == 404:
        raise FileNotFoundError(f"HTTP 404: {path} not found")
    if resp.status_code == 429:
        raise RuntimeError(f"HTTP 429: Rate limited — {resp.text[:300]}")
    if resp.status_code >= 500:
        raise RuntimeError(f"HTTP {resp.status_code}: Server error — {resp.text[:300]}")
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
    if resp.status_code == 204 or not resp.text:
        return {}
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def cleanup_vapi(dry_run: bool, include_tools: bool = False) -> dict[str, Any]:
    """List and optionally delete all Vapi assistants (and optionally tools)."""
    summary: dict[str, Any] = {
        "assistants": [],
        "tools": [],
        "deleted": 0,
        "failed": 0,
        "skipped": 0,
    }

    api_key = os.getenv("VAPI_API_KEY")
    if not api_key:
        print(c("\n  Vapi — not configured (VAPI_API_KEY missing), skipping.", YELLOW))
        summary["error"] = "VAPI_API_KEY missing"
        return summary

    # Prefer adapter for delete (has validation), use raw GET for list
    try:
        from adapters.vapi import VapiAdapter

        vapi_adapter = VapiAdapter()
    except Exception:
        vapi_adapter = None  # type: ignore

    print(c("\n  Vapi — assistants", BOLD))
    try:
        data = _vapi_request("GET", "/assistant", api_key)
        # Vapi returns array or {assistants: []} depending on version
        if isinstance(data, list):
            assistants = data
        elif isinstance(data, dict) and isinstance(data.get("assistants"), list):
            assistants = data["assistants"]
        else:
            assistants = data if isinstance(data, list) else []

        print(f"    Found {len(assistants)} assistant(s)")
        for a in assistants:
            aid = a.get("id", "?")
            name = a.get("name", "?")
            model = (
                (a.get("model") or {}).get("model", "?")
                if isinstance(a.get("model"), dict)
                else "?"
            )
            print(f"      • [{aid}] {name}  model={model}")
            summary["assistants"].append(a)

        if not dry_run:
            for a in assistants:
                aid = str(a["id"])
                name = a.get("name", aid)
                try:
                    if vapi_adapter:
                        vapi_adapter.delete_assistant(aid)
                    else:
                        _vapi_request("DELETE", f"/assistant/{aid}", api_key)
                    print(c(f"      ✓ Deleted assistant [{aid}] {name}", GREEN))
                    summary["deleted"] += 1
                    time.sleep(0.4)
                except FileNotFoundError:
                    print(c(f"      ○ Already gone [{aid}] {name}", YELLOW))
                    summary["deleted"] += 1
                except Exception as e:
                    msg = str(e)
                    if "404" in msg or "Not found" in msg:
                        print(c(f"      ○ Already gone [{aid}] {name}", YELLOW))
                        summary["deleted"] += 1
                    elif "429" in msg:
                        print(c(f"      ! Rate limited [{aid}], backing off 3s…", YELLOW))
                        time.sleep(3)
                        try:
                            if vapi_adapter:
                                vapi_adapter.delete_assistant(aid)
                            else:
                                _vapi_request("DELETE", f"/assistant/{aid}", api_key)
                            print(c(f"      ✓ Deleted on retry [{aid}] {name}", GREEN))
                            summary["deleted"] += 1
                        except Exception as e2:
                            print(c(f"      ✗ Failed [{aid}] {name}: {e2}", RED))
                            summary["failed"] += 1
                    else:
                        print(c(f"      ✗ Failed [{aid}] {name}: {e}", RED))
                        summary["failed"] += 1
        else:
            print(c("    (dry-run — no deletes)", CYAN))
            summary["skipped"] = len(assistants)

    except PermissionError as e:
        print(c(f"    ✗ Vapi auth failed: {e}", RED))
        summary["error"] = str(e)
    except Exception as e:
        print(c(f"    ✗ list/delete assistants failed: {e}", RED))
        summary["error"] = str(e)

    # Optionally clean tools (off by default — tools may be shared)
    if include_tools:
        print(c("\n  Vapi — tools", BOLD))
        try:
            # Adapter has list_tools
            if vapi_adapter:
                receipt = vapi_adapter.list_tools(limit=100)
                tools = receipt.response_data.get("tools", [])
            else:
                data = _vapi_request("GET", "/tool", api_key)
                tools = (
                    data
                    if isinstance(data, list)
                    else data.get("tools", [])
                    if isinstance(data, dict)
                    else []
                )

            print(f"    Found {len(tools)} tool(s)")
            for t in tools:
                tid = t.get("id", "?")
                name = (t.get("function") or {}).get("name", t.get("name", "?"))
                print(f"      • [{tid}] {name}")
                summary["tools"].append(t)

            if not dry_run:
                for t in tools:
                    tid = str(t["id"])
                    tname = (t.get("function") or {}).get("name", tid)
                    try:
                        _vapi_request("DELETE", f"/tool/{tid}", api_key)
                        print(c(f"      ✓ Deleted tool [{tid}] {tname}", GREEN))
                        summary["deleted"] += 1
                        time.sleep(0.35)
                    except FileNotFoundError:
                        print(c(f"      ○ Already gone tool [{tid}] {tname}", YELLOW))
                        summary["deleted"] += 1
                    except Exception as e:
                        if "404" in str(e):
                            print(c(f"      ○ Already gone tool [{tid}] {tname}", YELLOW))
                            summary["deleted"] += 1
                        else:
                            print(c(f"      ✗ Failed tool [{tid}] {tname}: {e}", RED))
                            summary["failed"] += 1
            else:
                print(c("    (dry-run — no deletes)", CYAN))
                summary["skipped"] += len(tools)
        except Exception as e:
            print(c(f"    ✗ list/delete tools failed: {e}", RED))
            summary["tools_error"] = str(e)
    else:
        print(c("\n  Vapi — tools: skipped (use --include-tools to wipe tools too)", CYAN))

    # Phone numbers are NOT deleted — they are account-level. We unassign instead if needed.
    # List them for visibility.
    try:
        from adapters.vapi import VapiAdapter as _va_adapter  # noqa: N814, N813

        va = _va_adapter()
        receipt = va.list_phone_numbers()
        numbers = receipt.response_data.get("phone_numbers", [])
        if numbers:
            print(c(f"\n  Vapi — phone numbers ({len(numbers)} found, NOT deleted):", YELLOW))
            for n in numbers:
                nid = n.get("id", "?")
                num = n.get("number", n.get("phoneNumber", "?"))
                aid = n.get("assistantId", "unassigned")
                print(f"      • [{nid}] {num}  → assistant={aid}")
            print(
                c(
                    "     Phone numbers are account-level and are NOT deleted by this script.",
                    YELLOW,
                )
            )
            print(c("     To unassign: PATCH /phone-number/{id} with {assistantId: null}", YELLOW))
    except Exception:
        pass

    return summary


# ── Render / hosting ─────────────────────────────────────────────────────


def cleanup_hosting(dry_run: bool) -> dict[str, Any]:
    """Render has no safe bulk-delete; report and optionally suspend service."""
    summary: dict[str, Any] = {"deleted": 0, "failed": 0, "skipped": 0}

    token = os.getenv("HOSTING_API_TOKEN")
    service_id = os.getenv("HOSTING_SERVICE_ID")
    health_url = os.getenv("HOSTING_HEALTH_URL")

    print(c("\n  Render / hosting", BOLD))
    if not token or not service_id:
        print(
            c(
                "    Not configured (HOSTING_API_TOKEN / HOSTING_SERVICE_ID missing) — skipping.",
                YELLOW,
            )
        )
        if health_url:
            print(f"    Health URL on record: {health_url}  (not deleted)")
        summary["error"] = "not configured"
        return summary

    # We deliberately do NOT delete the Render service by default.
    # Render DELETE /v1/services/{id} is destructive and not in the adapter contract.
    # Instead we report the service and offer a manual step.
    print(f"    Service ID: {service_id}")
    if health_url:
        print(f"    Health URL: {health_url}")
    print(c("    Render service deletion is DESTRUCTIVE and NOT performed by default.", YELLOW))
    print(
        c(
            "    The backend code + Supabase schemas are local artifacts — not remote deletes.",
            YELLOW,
        )
    )
    print("    To delete the Render service manually:")
    print(c(f"      curl -X DELETE https://api.render.com/v1/services/{service_id} \\", CYAN))
    print(c("        -H 'Authorization: Bearer $HOSTING_API_TOKEN'", CYAN))
    print("    Or delete it from the Render dashboard.")

    # Optional: suspend service (POST /services/{id}/suspend) if --suspend-hosting passed
    # Handled by caller flag — here we just report.
    return summary


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> int:
    p = argparse.ArgumentParser(
        description="Wipe ALL staging resources (Make scenarios/hooks, Vapi assistants, report hosting).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python scripts/cleanup_all.py
  python scripts/cleanup_all.py --execute
  python scripts/cleanup_all.py --execute --yes --only make
  python scripts/cleanup_all.py --execute --yes --skip hosting
  python scripts/cleanup_all.py --execute --yes --include-tools
        """,
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True, help="Preview only (default)")
    g.add_argument("--execute", action="store_true", help="Actually delete (requires confirmation)")
    p.add_argument("--yes", "-y", action="store_true", help="Skip interactive DELETE ALL prompt")
    p.add_argument(
        "--force-production", action="store_true", help="Allow when AGENT_FORGE_ENV=production"
    )
    p.add_argument("--only", choices=["make", "vapi", "hosting"], help="Only clean this platform")
    p.add_argument(
        "--skip",
        action="append",
        choices=["make", "vapi", "hosting"],
        default=[],
        help="Skip platform (repeatable)",
    )
    p.add_argument(
        "--include-tools", action="store_true", help="Also delete all Vapi tools (off by default)"
    )
    p.add_argument(
        "--suspend-hosting",
        action="store_true",
        help="Suspend Render service (not delete) when cleaning hosting",
    )
    args = p.parse_args()

    dry_run = not args.execute
    if args.execute:
        args.dry_run = False
        dry_run = False

    env_guard(args.force_production)

    only = args.only
    skip = set(args.skip or [])

    def should_run(platform: str) -> bool:
        if only and platform != only:
            return False
        return platform not in skip

    print(c("\n" + "=" * 70, BOLD))
    print(c("  AGENT FORGE — FULL ENVIRONMENT CLEANUP", BOLD))
    print(c("=" * 70, BOLD))
    print(
        f"  Mode:        {c('DRY-RUN (no deletes)', CYAN) if dry_run else c('EXECUTE — will delete', RED + BOLD)}"
    )
    print(f"  Environment: {os.getenv('AGENT_FORGE_ENV', 'staging')}")
    print(
        f"  Make:        {os.getenv('MAKE_ZONE', '?')}.make.com  team={os.getenv('MAKE_TEAM_ID', '?')}"
    )
    print(f"  Vapi:        api.vapi.ai  key={'set' if os.getenv('VAPI_API_KEY') else 'MISSING'}")
    print(f"  Hosting:     service={os.getenv('HOSTING_SERVICE_ID', '?')}")
    print(
        f"  Scope:       {only or 'all'}  skip={list(skip) or 'none'}  include_tools={args.include_tools}"
    )
    print(c("=" * 70, BOLD))

    # ── Discovery pass (counts for confirmation) ──
    # For confirmation we want the total count before deleting. Do a lightweight
    # discovery without deletes, then confirm, then re-list inside each cleanup
    # (which handles its own listing). So we just show what WILL be discovered.
    # To avoid double API calls, the cleaners themselves list again — here we
    # only estimate for the prompt when counting is cheap. Simpler: just run
    # cleaners which print counts, but confirmation must come BEFORE deletes.
    # So: list first in dry-run style, confirm, then delete.

    # We achieve this by: if execute and not --yes, do a pre-flight list,
    # confirm, then run again with deletes. For now the cleaners list then
    # delete in one pass — so we confirm BEFORE calling them when not --yes.
    # Pre-flight: peek counts without deleting by calling list endpoints directly.

    total_estimate = 0
    if not dry_run and not args.yes:
        print(c("\n  Pre-flight discovery (no deletes yet)…", CYAN))
        if should_run("make"):
            try:
                from adapters.make import MakeAdapter

                ma = MakeAdapter()
                sc = ma.list_scenarios().response_data.get("scenarios", [])
                hk = ma.list_hooks().response_data.get("hooks", [])
                total_estimate += len(sc) + len(hk)
                print(f"    Make: {len(sc)} scenario(s), {len(hk)} hook(s)")
            except Exception as e:
                print(c(f"    Make pre-flight failed: {e}", YELLOW))
        if should_run("vapi"):
            try:
                data = _vapi_request("GET", "/assistant", os.getenv("VAPI_API_KEY", ""))
                assistants = (
                    data
                    if isinstance(data, list)
                    else data.get("assistants", [])
                    if isinstance(data, dict)
                    else []
                )
                total_estimate += len(assistants)
                print(f"    Vapi: {len(assistants)} assistant(s)")
                if args.include_tools:
                    from adapters.vapi import VapiAdapter

                    va = VapiAdapter()
                    tools = va.list_tools(limit=100).response_data.get("tools", [])
                    total_estimate += len(tools)
                    print(f"    Vapi tools: {len(tools)}")
            except Exception as e:
                print(c(f"    Vapi pre-flight failed: {e}", YELLOW))
        print(f"    Estimated total to delete: {total_estimate}")
        if not confirm_destructive(total_estimate, dry_run=False):
            print(c("\n  Aborted — no changes made.", YELLOW))
            return 0
    elif not dry_run and args.yes:
        print(c("\n  --yes: skipping interactive confirmation.", YELLOW))

    # ── Execute cleaners ──
    totals = {"deleted": 0, "failed": 0, "skipped": 0}
    errors: list[str] = []

    if should_run("make"):
        print(c("\n" + "─" * 70, CYAN))
        print(c("  [1/3] Make.com — scenarios & hooks", BOLD))
        print(c("─" * 70, CYAN))
        r = cleanup_make(dry_run=dry_run)
        totals["deleted"] += r.get("deleted", 0)
        totals["failed"] += r.get("failed", 0)
        totals["skipped"] += r.get("skipped", 0)
        if r.get("error"):
            errors.append(f"make: {r['error']}")
    else:
        print(c("\n  [1/3] Make — skipped", YELLOW))

    if should_run("vapi"):
        print(c("\n" + "─" * 70, CYAN))
        print(c("  [2/3] Vapi — assistants" + (" + tools" if args.include_tools else ""), BOLD))
        print(c("─" * 70, CYAN))
        r = cleanup_vapi(dry_run=dry_run, include_tools=args.include_tools)
        totals["deleted"] += r.get("deleted", 0)
        totals["failed"] += r.get("failed", 0)
        totals["skipped"] += r.get("skipped", 0)
        if r.get("error"):
            errors.append(f"vapi: {r['error']}")
    else:
        print(c("\n  [2/3] Vapi — skipped", YELLOW))

    if should_run("hosting"):
        print(c("\n" + "─" * 70, CYAN))
        print(c("  [3/3] Hosting / backend", BOLD))
        print(c("─" * 70, CYAN))
        r = cleanup_hosting(dry_run=dry_run)
        # Optional suspend if requested and executing
        if args.suspend_hosting and not dry_run:
            try:
                import requests

                token = os.getenv("HOSTING_API_TOKEN", "")
                sid = os.getenv("HOSTING_SERVICE_ID", "")
                if token and sid:
                    url = f"https://api.render.com/v1/services/{sid}/suspend"
                    resp = requests.post(
                        url, headers={"Authorization": f"Bearer {token}"}, timeout=(10, 30)
                    )
                    if resp.status_code in (200, 202, 204):
                        print(c(f"    ✓ Service {sid} suspended.", GREEN))
                    else:
                        print(
                            c(
                                f"    ✗ Suspend failed HTTP {resp.status_code}: {resp.text[:300]}",
                                RED,
                            )
                        )
                        totals["failed"] += 1
                else:
                    print(c("    ! Cannot suspend — HOSTING_API_TOKEN/SERVICE_ID missing", YELLOW))
            except Exception as e:
                print(c(f"    ✗ Suspend failed: {e}", RED))
                totals["failed"] += 1
        totals["deleted"] += r.get("deleted", 0)
        totals["failed"] += r.get("failed", 0)
        totals["skipped"] += r.get("skipped", 0)
    else:
        print(c("\n  [3/3] Hosting — skipped", YELLOW))

    # ── Summary ──
    print(c("\n" + "=" * 70, BOLD))
    print(c("  CLEANUP SUMMARY", BOLD))
    print(c("=" * 70, BOLD))
    if dry_run:
        print("  Mode:     DRY-RUN — no deletes performed")
        print(f"  Would skip (matched): {totals['skipped']} resource(s)")
        if totals["failed"]:
            print(c(f"  Errors during discovery: {totals['failed']}", YELLOW))
        print(c("\n  To actually delete, run:", CYAN))
        print(c("    python scripts/cleanup_all.py --execute", BOLD))
        print(c("    python scripts/cleanup_all.py --execute --yes   # no prompt", CYAN))
    else:
        print(f"  Deleted:  {totals['deleted']}")
        if totals["failed"]:
            print(c(f"  Failed:   {totals['failed']}", RED))
        if totals["skipped"]:
            print(f"  Skipped:  {totals['skipped']}")
        if errors:
            print(c(f"\n  Warnings: {'; '.join(errors)}", YELLOW))
        if totals["failed"] == 0 and totals["deleted"] > 0:
            print(c("\n  ✓ Cleanup complete.", GREEN + BOLD))
        elif totals["failed"] == 0 and totals["deleted"] == 0:
            print(c("\n  ○ Nothing to delete — environment already clean.", YELLOW))
        else:
            print(c("\n  ⚠ Cleanup completed with errors — check output above.", YELLOW))
    print(c("=" * 70, BOLD) + "\n")

    if not dry_run and totals["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    enable_utf8_output()
    sys.exit(main())
