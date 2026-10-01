"""Import the CLI-named acceptance helper without running its main function."""
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('niri_e2e',Path(__file__).with_name('niri-e2e.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
MCP = module.MCP
eventually = module.eventually
