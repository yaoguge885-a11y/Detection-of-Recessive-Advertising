"""Local, single-annotator HTML workbench for the recessive-advertising study.

The package deliberately uses only the Python standard library.  Ollama access
is isolated in :mod:`annotation_workbench.ollama_bridge` and reuses the existing
``auto_judge`` module rather than duplicating its prompt or label contract.
"""

__version__ = "0.1.0"
