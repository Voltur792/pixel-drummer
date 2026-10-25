from pathlib import Path
import tomllib

# plugin.toml is the only place `astra-plugin version` rewrites; never repeat the number elsewhere.
VERSION = tomllib.loads((Path(__file__).resolve().parents[1] / "plugin.toml").read_text(encoding="utf-8"))["plugin"]["version"]
