"""Expected rejections raised inside a staging transaction.

A Rejection means the input must not be staged (unknown version, failed gate,
conflict). It writes nothing, including to processing_status. Any other
exception inside a transaction is an unexpected processing error, recorded as
a technical failure for a registered version (Requirement 14.7).
"""


class Rejection(Exception):
    pass
