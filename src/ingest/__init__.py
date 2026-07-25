"""Data acquisition: the ONLY place that talks to the network.

Business logic never imports this directly with a live connection; clients take
an injected ``get_json`` callable so the whole layer is testable offline.
"""
