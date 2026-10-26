"""
A test app for LLM access (opt-in with runtime.llm in app.yml).

It records what LLM access the step was given (LLM_GOVERNOR_FUNCTION_NAME,
ANTHROPIC_BASE_URL, the sidecar on localhost:8765), asks Claude through the
sidecar for a one-sentence summary of the files in INPUT_DIR, and writes
OUTPUT_DIR/llm-result.json. With REQUIRE_LLM (the default) the run fails when
access is missing or the call fails, so the run's status is the test.
"""
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("test-llm-probe")

MAX_INPUT_CHARS = 6000


def input_text(input_dir):
    """The input's files, as text, up to MAX_INPUT_CHARS."""
    parts, files = [], []
    for dirpath, _, names in os.walk(input_dir, followlinks=True):
        for name in sorted(names):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, input_dir)
            files.append(rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    parts.append(f"--- {rel}\n{f.read(MAX_INPUT_CHARS)}")
            except OSError as err:
                parts.append(f"--- {rel} (unreadable: {err})")
    return "\n".join(parts)[:MAX_INPUT_CHARS], sorted(files)


def ask(base_url, token, model, text):
    """POST /v1/messages to the sidecar: (status, body as a dict)."""
    body = json.dumps({
        "model": model,
        "max_tokens": 200,
        "messages": [{
            "role": "user",
            "content": "In one sentence, say what these files describe.\n\n" + text,
        }],
    }).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": token or "placeholder",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read() or b"{}")
        except ValueError:
            return err.code, {}
    except (urllib.error.URLError, OSError) as err:
        return 0, {"error": str(err)}


def allowed_models(body):
    """The models a model_not_allowed answer lists, wherever it puts them."""
    for holder in (body, body.get("error") if isinstance(body.get("error"), dict) else {}):
        models = holder.get("allowedModels") if isinstance(holder, dict) else None
        if models:
            return list(models)
    return []


def main():
    input_dir = os.environ.get("INPUT_DIR", "")
    output_dir = os.environ.get("OUTPUT_DIR", "")
    model = os.environ.get("MODEL") or "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    require = os.environ.get("REQUIRE_LLM", "true").lower() == "true"
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    if not output_dir:
        log.error("OUTPUT_DIR must be set")
        return 2

    result = {
        "app": "test-llm-probe",
        "at": datetime.now(timezone.utc).isoformat(),
        "llmAccess": {
            "LLM_GOVERNOR_FUNCTION_NAME": bool(os.environ.get("LLM_GOVERNOR_FUNCTION_NAME")),
            "ANTHROPIC_BASE_URL": base_url,
        },
        "attempts": [],
        "ok": False,
    }
    text, files = input_text(input_dir) if input_dir and os.path.isdir(input_dir) else ("", [])
    result["inputFiles"] = files

    if not base_url:
        result["error"] = "no ANTHROPIC_BASE_URL: the step was given no LLM access"
    else:
        # The allow-list a 403 names is kept, so a model that fails another
        # way (a retired one answers 404 from Bedrock) falls through to the
        # next allowed one.
        tried, allowed = [], []
        while model and model not in tried and len(tried) < 5:
            tried.append(model)
            status, body = ask(base_url, os.environ.get("ANTHROPIC_AUTH_TOKEN"), model, text or "(no input files)")
            attempt = {"model": model, "status": status}
            if status == 200:
                content = body.get("content") or []
                attempt["summary"] = " ".join(c.get("text", "") for c in content if isinstance(c, dict)).strip()
                attempt["usage"] = body.get("usage")
                result["attempts"].append(attempt)
                result["ok"] = bool(attempt["summary"])
                result["model"] = model
                result["summary"] = attempt["summary"]
                break
            attempt["error"] = body
            result["attempts"].append(attempt)
            allowed = allowed_models(body) or allowed
            left = [m for m in allowed if m not in tried]
            haiku = [m for m in left if "haiku" in m]
            model = (haiku or left or [None])[0]
        if not result["ok"]:
            result["error"] = "the model call failed (see attempts)"

    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "llm-result.json"), "w") as out:
        json.dump(result, out, indent=2)

    log.info("LLM access: %s", result["llmAccess"])
    for a in result["attempts"]:
        log.info("asked %s: HTTP %s %s", a["model"], a["status"], a.get("summary") or a.get("error"))
    if result["ok"]:
        log.info("summary from %s: %s", result["model"], result["summary"])
        return 0
    log.error("%s", result.get("error"))
    return 1 if require else 0


if __name__ == "__main__":
    sys.exit(main())
