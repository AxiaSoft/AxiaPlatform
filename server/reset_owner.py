"""Get back into the console when the owner's password no longer works.

    python3 server/reset_owner.py

Why this is a command and not a button: the person who can reset the account
that manages every other administrator must be someone with access to the
server itself. A reset link sent by email would need a mail server, and a
"forgot password" page in a product with no email would have to reveal whether
an address exists - so it would either be useless or a way to enumerate
administrators. One command, run where the database lives, is the smaller
surface and the honest one.

What it does:

  * Finds the owner - the administrator whose ``admin_role`` is 'owner', or the
    oldest administrator if no role was ever recorded (a database from before
    roles existed).
  * Takes a new password, at least 12 characters, typed twice.
  * Revokes every session that account had, so anything already signed in with
    the lost password stops working immediately.
  * Prints what it did, and never the password.

It refuses to invent an owner when there is already a working one. Creating a
second owner silently is how a product ends up with an administrator nobody
knows about; ``provision_admin.py`` is the command that creates one on purpose.
"""
import getpass
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    from app import hash_password
    from db import connect, init
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        f'Could not import the server modules from {_HERE} ({exc}).\n'
        'Run this from the repository root:\n'
        '    python3 server/reset_owner.py'
    )


def find_owner(conn):
    """The account this command resets.

    A database that predates the admin_role column has no owner recorded, so
    the oldest administrator is treated as one - which is what every such
    installation effectively has.
    """
    row = conn.execute(
        "SELECT id,name,email FROM users WHERE role='admin' AND admin_role='owner' "
        "ORDER BY id LIMIT 1").fetchone()
    if row:
        return row
    return conn.execute(
        "SELECT id,name,email FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()


def main():
    init()
    conn = connect()
    try:
        owner = find_owner(conn)
        if not owner:
            print('There is no administrator in this database.')
            print('Create one with:  python3 server/provision_admin.py')
            return 1
        print(f'Resetting the password for the owner: {owner["email"]} (id {owner["id"]}).')
        answer = input('Type COPY_ME_IS_OWNER to confirm: ').strip()
        if answer != 'COPY_ME_IS_OWNER':
            print('No changes made.')
            return 1
        password = getpass.getpass('New password (at least 12 characters): ')
        confirm = getpass.getpass('Confirm password: ')
        if len(password) < 12:
            print('Choose a password of at least 12 characters.')
            return 1
        if password != confirm:
            print('Passwords did not match.')
            return 1
        conn.execute("UPDATE users SET password_hash=?, role='admin', admin_role='owner', active=1 "
                     'WHERE id=?', (hash_password(password), owner['id']))
        # Anything signed in with the password we just replaced is signed out.
        revoked = conn.execute('DELETE FROM sessions WHERE user_id=?', (owner['id'],)).rowcount
        conn.commit()
        print(f'Password changed. {revoked} session(s) revoked.')
        print('Sign in at /admin/. The password was not stored or printed.')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
