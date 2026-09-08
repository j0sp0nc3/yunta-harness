#!/usr/bin/env python3
"""
Diagnostic script for Yunta harness model endpoints & JWT authentication.
Validates .yunta/config.json, JWT token health, and tests connectivity
against OpenAI-compatible endpoints with detailed HTTP error diagnosis.

Usage:
    python scripts/check_endpoints.py [--config .yunta/config.json]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def decode_jwt_unverified(token: str) -> tuple[dict, dict]:
    """Decodes JWT header and payload without verifying signature."""
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError(f"JWT must contain 3 parts separated by '.', found {len(parts)}")

    def b64_decode(segment: str) -> dict:
        padded = segment + "=" * (-len(segment) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        return json.loads(raw.decode("utf-8", errors="replace"))

    header = b64_decode(parts[0])
    payload = b64_decode(parts[1])
    return header, payload


def check_jwt_health(token_path_or_str: str) -> dict:
    """Evaluates JWT token validity, expiration, issuer and scopes."""
    p = Path(token_path_or_str)
    if p.exists() and p.is_file():
        raw_token = p.read_text(encoding="utf-8").strip()
        source = f"File: {p}"
    else:
        raw_token = token_path_or_str.strip()
        source = "Raw token / Environment"

    if not raw_token:
        return {"status": "error", "error": "Token is empty", "source": source}

    try:
        header, payload = decode_jwt_unverified(raw_token)
    except Exception as e:
        return {"status": "error", "error": f"Failed to parse JWT: {e}", "source": source}

    now = int(time.time())
    exp = payload.get("exp")
    iat = payload.get("iat")
    iss = payload.get("iss", "N/A")
    sub = payload.get("sub", "N/A")
    scopes = payload.get("scope") or payload.get("scopes") or payload.get("permissions") or []

    is_expired = False
    expires_in_seconds = None
    exp_iso = "No expiration (None)"

    if exp is not None:
        try:
            exp_val = int(exp)
            expires_in_seconds = exp_val - now
            is_expired = expires_in_seconds <= 0
            exp_iso = datetime.fromtimestamp(exp_val, tz=timezone.utc).isoformat()
        except (ValueError, TypeError):
            exp_iso = f"Invalid exp value: {exp}"

    return {
        "status": "expired" if is_expired else "valid",
        "source": source,
        "is_expired": is_expired,
        "expires_in_seconds": expires_in_seconds,
        "exp_iso": exp_iso,
        "iss": iss,
        "sub": sub,
        "scopes": scopes,
        "algorithm": header.get("alg", "N/A"),
        "raw_token": raw_token,
    }


def normalize_base_url(base_url: str) -> str:
    """Ensures baseURL ends properly without trailing slash."""
    url = base_url.strip()
    if url.endswith("/"):
        url = url[:-1]
    return url


def probe_endpoint(base_url: str, model_id: str, token: str | None = None, timeout: float = 8.0) -> dict:
    """Probes endpoint with GET /models and minimal POST /chat/completions."""
    norm_url = normalize_base_url(base_url)

    # 1. Probe /models
    models_url = f"{norm_url}/models" if not norm_url.endswith("/models") else norm_url
    headers = {"Content-Type": "application/json"}
    if token:
        bearer = token if token.lower().startswith("bearer ") else f"Bearer {token}"
        headers["Authorization"] = bearer

    req_models = urllib.request.Request(models_url, headers=headers, method="GET")

    start = time.time()
    try:
        with urllib.request.urlopen(req_models, timeout=timeout) as resp:
            elapsed = time.time() - start
            body = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
                models_list = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
            except Exception:
                models_list = []
            return {
                "http_status": resp.status,
                "elapsed_s": elapsed,
                "url_tested": models_url,
                "success": True,
                "models_available": models_list,
                "diagnosis": "OK: Endpoint is reachable and authenticated.",
            }
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        err_body = e.read().decode("utf-8", errors="replace")[:300]
        status = e.code

        if status == 404:
            diag = (
                "404 NOT FOUND: The path does not exist. Verify baseURL.\n"
                "  - Check if endpoint needs '/v1' (e.g. http://host:port/v1).\n"
                "  - Ensure the path is not duplicated (e.g. avoid /v1/v1)."
            )
        elif status == 401:
            diag = (
                "401 UNAUTHORIZED: Authentication failed.\n"
                "  - JWT token is invalid, expired, revoked, or missing Bearer prefix."
            )
        elif status == 403:
            diag = (
                "403 FORBIDDEN: Authenticated, but lacks permissions.\n"
                "  - Token lacks required scope or model access is restricted."
            )
        elif status == 400:
            diag = (
                "400 BAD REQUEST: Server rejected request format or headers.\n"
                "  - Check if server expects custom headers or strict OpenAI JSON schema."
            )
        elif status == 503:
            diag = (
                "503 SERVICE UNAVAILABLE: Provider or gateway is down or overloaded.\n"
                "  - Model runner / cluster may be starting up, scaled to 0, or offline."
            )
        else:
            diag = f"HTTP {status}: {err_body}"

        return {
            "http_status": status,
            "elapsed_s": elapsed,
            "url_tested": models_url,
            "success": False,
            "error_body": err_body,
            "diagnosis": diag,
        }
    except urllib.error.URLError as e:
        elapsed = time.time() - start
        return {
            "http_status": 0,
            "elapsed_s": elapsed,
            "url_tested": models_url,
            "success": False,
            "error_body": str(e.reason),
            "diagnosis": f"NETWORK / DNS ERROR: Cannot connect to {norm_url}. Reason: {e.reason}",
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "http_status": 0,
            "elapsed_s": elapsed,
            "url_tested": models_url,
            "success": False,
            "error_body": str(e),
            "diagnosis": f"UNEXPECTED ERROR: {type(e).__name__}: {e}",
        }


def main():
    parser = argparse.ArgumentParser(description="Diagnose Yunta model endpoints & JWT authentication")
    parser.add_argument("--config", "-c", default=".yunta/config.json", help="Path to .yunta/config.json")
    args = parser.parse_args()

    print("=" * 70)
    print("🔍 YUNTA HARNESS — ENDPOINT & AUTHENTICATION DIAGNOSTIC TOOL")
    print("=" * 70)

    cfg_path = Path(args.config)
    config = {}

    if cfg_path.exists():
        print(f"📄 Configuration file found: {cfg_path.resolve()}")
        try:
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"❌ Error parsing {cfg_path}: {e}")
            sys.exit(1)
    else:
        print(f"⚠️  Configuration file '{args.config}' not found.")
        print("   Falling back to environment variables (LLM_API_BASE, LLM_MODEL, LLM_API_KEY)...")
        env_base = os.environ.get("LLM_API_BASE")
        env_model = os.environ.get("LLM_MODEL", "openai/custom")
        env_key = os.environ.get("LLM_API_KEY", "")
        if env_base:
            config = {
                "endpoints": [
                    {
                        "name": "env_default",
                        "baseURL": env_base,
                        "model": env_model,
                        "auth": {"type": "bearer", "token": env_key} if env_key else {},
                    }
                ]
            }
        else:
            print("\n❌ No configuration found in .yunta/config.json or LLM_API_BASE.")
            print("   Please create .yunta/config.json or define LLM_API_BASE.")
            sys.exit(1)

    # 1. Validate JWT / Auth
    token_to_use = None
    auth_section = config.get("auth") or {}
    token_file = auth_section.get("token_file") or config.get("token_file")

    print("\n[1] VALIDATING AUTHENTICATION & JWT HEALTH")
    print("-" * 50)

    if token_file:
        print(f"Checking configured token file: {token_file}")
        jwt_info = check_jwt_health(token_file)
        print(f"  • Source:     {jwt_info.get('source')}")
        if jwt_info.get("status") == "error":
            print(f"  • ❌ Error:   {jwt_info.get('error')}")
        else:
            exp_status = "❌ EXPIRED" if jwt_info.get("is_expired") else "✅ VALID"
            print(f"  • Status:     {exp_status}")
            print(f"  • Algorithm:  {jwt_info.get('algorithm')}")
            print(f"  • Issuer:     {jwt_info.get('iss')}")
            print(f"  • Subject:    {jwt_info.get('sub')}")
            print(f"  • Expires At: {jwt_info.get('exp_iso')}")
            if not jwt_info.get("is_expired") and jwt_info.get("expires_in_seconds"):
                mins_left = jwt_info.get("expires_in_seconds") // 60
                print(f"  • Remaining:  ~{mins_left} minutes")
            token_to_use = jwt_info.get("raw_token")
    else:
        inline_token = auth_section.get("token") or os.environ.get("LLM_API_KEY")
        if inline_token:
            if inline_token.count(".") == 2:
                jwt_info = check_jwt_health(inline_token)
                exp_status = "❌ EXPIRED" if jwt_info.get("is_expired") else "✅ VALID"
                print(f"  • Inline JWT Status: {exp_status} (Expires: {jwt_info.get('exp_iso')})")
            else:
                print("  • API Key / Non-JWT token provided (opaque key format).")
            token_to_use = inline_token
        else:
            print("  • ⚠️ No authentication token specified (testing unauthenticated endpoints).")

    # 2. Check Endpoints
    endpoints = config.get("endpoints") or []
    if not endpoints and config.get("baseURL"):
        endpoints = [{"name": "primary", "baseURL": config["baseURL"], "model": config.get("model", "default")}]

    print(f"\n[2] TESTING ENDPOINT CONNECTIVITY ({len(endpoints)} configured)")
    print("-" * 50)

    results = []
    for idx, ep in enumerate(endpoints, start=1):
        name = ep.get("name", f"endpoint_{idx}")
        base_url = ep.get("baseURL") or ep.get("url") or ""
        model_id = ep.get("model") or ep.get("model_id") or "default"
        ep_token = ep.get("token") or token_to_use

        print(f"\nTesting Endpoint [{idx}/{len(endpoints)}]: '{name}'")
        print(f"  • Base URL: {base_url}")
        print(f"  • Model:    {model_id}")

        if not base_url:
            print("  • ❌ Error: Missing 'baseURL' for this endpoint.")
            results.append({"name": name, "status": "ERROR", "code": 0, "msg": "Missing baseURL"})
            continue

        res = probe_endpoint(base_url, model_id, ep_token)
        code = res["http_status"]
        status_label = "✅ PASS (200)" if res["success"] else f"❌ FAIL ({code})"
        print(f"  • Result:   {status_label} in {res['elapsed_s']:.2f}s")
        print(f"  • Analysis: {res['diagnosis']}")
        if res.get("models_available"):
            print(f"  • Models available on server: {', '.join(res['models_available'][:5])}")

        results.append({"name": name, "status": "PASS" if res["success"] else "FAIL", "code": code, "diag": res["diagnosis"]})

    # 3. Summary & Remediation
    print("\n" + "=" * 70)
    print("📋 SUMMARY & ACTIONABLE REMEDIATION PLAN")
    print("=" * 70)
    failed = [r for r in results if r["status"] != "PASS"]

    if not failed:
        print("🎉 ALL ENDPOINTS ARE HEALTHY AND REACHABLE! Yunta is ready to run.")
    else:
        print(f"⚠️  {len(failed)} of {len(results)} endpoint(s) returned errors:\n")
        for f in failed:
            print(f"  [!] {f['name']} -> HTTP {f['code']}")

        print("\n🔧 RECOMMENDED FIXES:")
        has_404 = any(f["code"] == 404 for f in failed)
        has_401 = any(f["code"] == 401 for f in failed)
        has_503 = any(f["code"] == 503 for f in failed)
        has_net = any(f["code"] == 0 for f in failed)

        if has_401:
            print("  1. AUTHENTICATION (401):")
            print("     - Refresh your JWT token file or re-authenticate.")
            print("     - Verify token has not expired and contains valid audience/issuer.")
        if has_404:
            print("  2. URL PATHS (404):")
            print("     - Ensure your baseURL points to the OpenAI API root (typically ending in '/v1').")
            print("     - Example: 'http://localhost:8000/v1' instead of 'http://localhost:8000'.")
        if has_503:
            print("  3. SERVICE AVAILABILITY (503):")
            print("     - Check the model server logs / GPU runner status.")
            print("     - Model may still be loading weights into VRAM.")
        if has_net:
            print("  4. NETWORK / FIREWALL (0):")
            print("     - Check host, port, VPN, or firewall rules blocking outgoing traffic.")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
