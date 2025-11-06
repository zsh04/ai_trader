#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC = Path(os.environ.get("CONTAINERS_SRC", BASE_DIR / "containers.appservice.json"))
DST = Path(
    os.environ.get("CONTAINERS_DST", BASE_DIR / "containers.appservice.rendered.json")
)


# --- simple comment stripper for //... and /* ... */ ---
def strip_json_comments(text: str) -> str:
    # remove /* ... */ (multi-line)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)

    # remove // ... (to end of line), but not within quotes
    def _strip_line(line):
        in_str = False
        esc = False
        out = []
        for i, ch in enumerate(line):
            if ch == '"' and not esc:
                in_str = not in_str
            if ch == "\\" and not esc:
                esc = True
                out.append(ch)
                continue
            if not in_str and ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                break
            out.append(ch)
            esc = False
        return "".join(out)

    return "\n".join(_strip_line(ln) for ln in text.splitlines())


def find_containers(doc):
    # new-ish shape: siteConfig.containers.containers (list)
    try:
        lst = doc["siteConfig"]["containers"]["containers"]
        if isinstance(lst, list):

            def setter(new):
                doc["siteConfig"]["containers"]["containers"] = new

            return lst, setter
    except Exception:
        pass
    # shape: properties.siteConfig.containers.containers (list)
    try:
        lst = doc["properties"]["siteConfig"]["containers"]["containers"]
        if isinstance(lst, list):

            def setter(new):
                doc["properties"]["siteConfig"]["containers"]["containers"] = new

            return lst, setter
    except Exception:
        pass
    # flat list variant: siteConfig.containers (list)
    try:
        lst = doc["siteConfig"]["containers"]
        if isinstance(lst, list):

            def setter(new):
                doc["siteConfig"]["containers"] = new

            return lst, setter
    except Exception:
        pass
    # flat list variant: properties.siteConfig.containers (list)
    try:
        lst = doc["properties"]["siteConfig"]["containers"]
        if isinstance(lst, list):

            def setter(new):
                doc["properties"]["siteConfig"]["containers"] = new

            return lst, setter
    except Exception:
        pass
    return None, None


def set_env(env_list, name, value):
    for item in env_list:
        if item.get("name") == name:
            item["value"] = value
            return
    env_list.append({"name": name, "value": value})


# ---- read & strip comments ----
try:
    raw = open(SRC, "r", encoding="utf-8").read()
except FileNotFoundError:
    print(f"ERROR: {SRC} not found", file=sys.stderr)
    sys.exit(2)

clean = strip_json_comments(raw)

try:
    data = json.loads(clean)
except json.JSONDecodeError as e:
    print(
        f"ERROR: {SRC} is not valid JSON after stripping comments: {e}", file=sys.stderr
    )
    sys.exit(2)

containers, set_back = find_containers(data)
if containers is None:
    print("ERROR: couldn't locate containers array in input JSON", file=sys.stderr)
    sys.exit(2)

# Resolve images (allow override)
app_image = os.environ.get("APP_IMAGE")
otel_image = os.environ.get("OTEL_IMAGE")
acr = os.environ.get("ACR_LOGIN_SERVER")
sha = os.environ.get("GITHUB_SHA")
if not app_image:
    if not (acr and sha):
        print(
            "ERROR: set APP_IMAGE or ACR_LOGIN_SERVER and GITHUB_SHA", file=sys.stderr
        )
        sys.exit(2)
    app_image = f"{acr}/ai-trader:{sha}"
if not otel_image and acr and sha:
    otel_image = f"{acr}/ai-trader-otel-collector:{sha}"

# Optional: embed otel config from env (already base64), or pass-through placeholder
otel_b64 = os.environ.get("OTEL_CONFIG_B64")

# Replace placeholders across containers + envs
for c in containers:
    name = c.get("name")
    if name == "app":
        # image
        c["image"] = app_image
        # envs
        envs = c.get("environmentVariables", [])
        replacements = {
            "__APP_VERSION__": os.environ.get("APP_VERSION", ""),
            "__DATABASE_URL__": os.environ.get("DATABASE_URL", ""),
            "__SENTRY_DSN__": os.environ.get("SENTRY_DSN", ""),
            "__GRAFANA_OTLP_ENDPOINT__": os.environ.get("GRAFANA_OTLP_ENDPOINT", ""),
            "__GRAFANA_BASIC_AUTH__": os.environ.get("GRAFANA_BASIC_AUTH", ""),
            "__TELEGRAM_TOKEN__": os.environ.get("TELEGRAM_TOKEN", ""),
            "__TELEGRAM_WEBHOOK_URL__": os.environ.get("TELEGRAM_WEBHOOK_URL", ""),
            "__TELEGRAM_WEBHOOK_SECRET__": os.environ.get(
                "TELEGRAM_WEBHOOK_SECRET", ""
            ),
        }
        # fill env vars by name match on "value" placeholder
        for ev in envs:
            val = ev.get("value")
            if isinstance(val, str) and val in replacements:
                ev["value"] = replacements[val]
        c["environmentVariables"] = envs

    elif name == "otel-collector" and otel_image:
        c["image"] = otel_image


# Replace volumes content if placeholder present
# path: siteConfig.containers.volumes or properties.siteConfig.containers.volumes
def find_volumes(doc):
    for path in (
        ("siteConfig", "containers", "volumes"),
        ("properties", "siteConfig", "containers", "volumes"),
    ):
        cur = doc
        ok = True
        for p in path:
            cur = cur.get(p)
            if cur is None:
                ok = False
                break
        if ok and isinstance(cur, list):
            return cur
    return None


vols = find_volumes(data)
if vols:
    for v in vols:
        content = v.get("content")
        if isinstance(content, dict) and content.get("base64") in (
            "__OTEL_CONFIG_B64__",
            None,
            "",
        ):
            if otel_b64:
                content["base64"] = otel_b64

# Write output
set_back(containers)
with open(DST, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f"Wrote {DST}")
