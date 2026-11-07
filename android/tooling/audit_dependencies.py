"""Fail-closed OSV audit of resolved Maven runtime coordinates, without extra packages."""

import json
import sys
import urllib.request
from pathlib import Path
from typing import Any


def audit(path: Path) -> None:
    coordinates = [line.split("\t") for line in path.read_text().splitlines() if line]
    if not coordinates or any(len(row) != 2 for row in coordinates):
        raise SystemExit("invalid/empty resolved dependency manifest")
    findings: list[dict[str, Any]] = []
    for start in range(0, len(coordinates), 100):
        group = coordinates[start : start + 100]
        queries = [
            {"package": {"ecosystem": "Maven", "name": name}, "version": version}
            for name, version in group
        ]
        request = urllib.request.Request(
            "https://api.osv.dev/v1/querybatch",
            data=json.dumps({"queries": queries}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise SystemExit("oversized OSV response")
        results = json.loads(raw)["results"]
        if len(results) != len(group):
            raise SystemExit("incomplete OSV response")
        for coordinate, result in zip(group, results, strict=True):
            if result.get("next_page_token"):
                raise SystemExit("OSV pagination requires manual review; refusing partial audit")
            if result.get("vulns"):
                findings.append({"coordinate": coordinate, "vulnerabilities": result["vulns"]})
    report = {
        "source": "https://api.osv.dev/v1/querybatch",
        "packages": len(coordinates),
        "findings": findings,
    }
    path.with_name("dependency-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"OSV: {len(coordinates)} runtime packages, {len(findings)} affected packages")
    if findings:
        print(json.dumps(findings, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    audit(Path(sys.argv[1]))
