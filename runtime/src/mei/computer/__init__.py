"""Computer use (architecture §10, decision 0022): the desktop worker and the core's side of it.

Modules the worker imports (`wire`, `geometry`, `worker/`) use only the standard library and PyGObject:
the worker runs on the system's Python, which has PyGObject, not on the runtime's.
"""
