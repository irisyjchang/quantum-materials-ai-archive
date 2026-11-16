"""Write transactions for review app routes.

Each recorded action runs in one BEGIN IMMEDIATE transaction on the request's
connection, so a failure at any point leaves the database unchanged.
"""

from contextlib import contextmanager


@contextmanager
def write_transaction(db):
    db.isolation_level = None
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    else:
        db.execute("COMMIT")
