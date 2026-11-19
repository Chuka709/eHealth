"""Reading lab results out of documents (Phase 4; docs/05, Q50).

Known lab layouts with a text layer are read here, locally - no AI, nothing leaves the server.
What a reader returns is raw text as printed (a draft, rule 4); numbers, ranges and flags are
worked out by `labtrack.core` (rule 6), never here.
"""
