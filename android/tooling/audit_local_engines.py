import ast
import collections
import hashlib
import json
import pathlib
import sys
from importlib.util import resolve_name
from typing import TypedDict


class ModuleAudit(TypedDict):
    path: str
    sha256_words: list[int]
    imports: list[str]


root = pathlib.Path("src/pocket_alpha")
modules: dict[str, ModuleAudit] = {}
for p in sorted(root.rglob("*.py")):
    name = "pocket_alpha." + ".".join(p.relative_to(root).with_suffix("").parts)
    if name.endswith(".__init__"):
        name = name[:-9]
    imports: set[str] = set()
    for n in ast.walk(ast.parse(p.read_text())):
        if isinstance(n, ast.Import):
            imports.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                package = name if p.name == "__init__.py" else name.rpartition(".")[0]
                imports.add(resolve_name("." * n.level + (n.module or ""), package))
            elif n.module:
                imports.add(n.module)
    modules[name] = {
        "path": str(p),
        "sha256_words": [
            int.from_bytes(hashlib.sha256(p.read_bytes()).digest()[i : i + 4], "big")
            for i in range(0, 32, 4)
        ],
        "imports": sorted(imports),
    }
output = {
    "baseline": "c3b843f",
    "method": (
        "AST import statements; conservative includes TYPE_CHECKING and optional imports; "
        "no runtime or Android compatibility proof"
    ),
    "module_count": len(modules),
    "external_roots": dict(
        sorted(
            collections.Counter(
                i.split(".")[0]
                for m in modules.values()
                for i in m["imports"]
                if not i.startswith("pocket_alpha")
            ).items()
        )
    ),
    "modules": modules,
}
destination = pathlib.Path("docs/tablet/IMPORT_AUDIT.json")
rendered = json.dumps(output, indent=2) + "\n"
if "--check" in sys.argv:
    if destination.read_text() != rendered:
        raise SystemExit("Engine import audit is stale; regenerate from repository root")
else:
    destination.write_text(rendered)
print(output["module_count"])
print(output["external_roots"])
