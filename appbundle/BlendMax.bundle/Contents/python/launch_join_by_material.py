import importlib
import sys
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import blendmax_actions

importlib.reload(blendmax_actions)
blendmax_actions.join_mesh_by_material()
