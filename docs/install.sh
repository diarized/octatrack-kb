#!/bin/bash
set -euo pipefail

# Installs the octatrack-kb MCP server for Claude launched in the current dir.
# Target: ./.claude/mcp.json — the file loaded via `claude --mcp-config` under a
# --strict-mcp-config launcher. Merges in, preserving any other servers present.

OKB="$(cd "$(dirname "$0")/.." && pwd)"
DST=.claude/mcp.json

mkdir -p .claude
[ -f "$DST" ] || echo '{"mcpServers":{}}' > "$DST"

OKB="$(cd "$(dirname "$0")/.." && pwd)"
import json, os, sys
dst, okb = sys.argv[1], os.environ["OKB"]
d = json.load(open(dst)); d.setdefault("mcpServers", {})
d["mcpServers"]["octatrack-kb"] = {
    "type": "stdio", "command": "uv",
    "args": ["run", "--directory", okb, "python", "-m", "server.octatrack_mcp"],
    "env": {
        "OCTATRACK_DB": f"{okb}/server/kb.db",
        "OCTATRACK_REFERENCE": f"{okb}/knowledge/reference",
        "OCTATRACK_CONCEPTS": f"{okb}/knowledge/concepts.yaml",
        "OCTATRACK_GUIDES": f"{okb}/knowledge/guides",
    },
}
json.dump(d, open(dst, "w"), indent=2)
print(f"Installed octatrack-kb -> {os.path.abspath(dst)}")
EOF

echo "Launch Claude in this dir (cc/ccr); /mcp will show octatrack-kb."
