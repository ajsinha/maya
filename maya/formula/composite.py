"""
``maya.formula.composite`` is ``maya.sdk._shared.formula_composite``: the same module, not a
copy.

It moved into the SDK because end users have the SDK without the rest of MAYA, and the SDK
and the server must share this code exactly (see ``maya.sdk._shared``). Importing this name
gives that module, private names and all.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

import sys
from typing import TYPE_CHECKING

from maya.sdk._shared import formula_composite as _shared

if TYPE_CHECKING:  # what this name is, for the type checker
    from maya.sdk._shared.formula_composite import *  # noqa: F403

sys.modules[__name__] = _shared
