"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The one MetaData every table registers itself against.

Its own module so that the subject files can each import it without importing
each other — a cycle here would be a schema that could only be loaded in one
order, which is exactly the property a declarative schema exists not to have.
"""
from __future__ import annotations

from sqlalchemy import MetaData

#: Every table in MAYA. `Database` applies it and compares against it;
#: nothing else should build DDL.
METADATA = MetaData()
