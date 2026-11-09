"""V3 project workspace: projects, requirement baseline, documents, findings.

Kept apart from the V2 run pipeline on purpose. V2 runs stay readable through
``/api/runs`` and their ``RunSnapshot`` storage; nothing here reads or writes
those tables.
"""
