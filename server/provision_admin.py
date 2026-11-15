"""Securely create or promote an administrator account for this development app.

Run it from the repository root:

    python3 server/provision_admin.py

or from inside server/:

    python3 provision_admin.py

Both work. `python3 -m server.provision_admin` also works, and that is the one
case that used to fail: run as a module, Python puts the *repository root* on
sys.path, so `from app import ...` looked for a top-level app.py and found the
project's own app.js next to none. The directory holding this file is added
explicitly below, which makes the import correct however the file is invoked,
and a clear error replaces the module traceback if the server files are
somewhere unexpected.
"""
import getpass
import os
import re
import sys

# `app` and `db` live beside this file, not beside the working directory. When
# this script is executed directly Python already knows that; when it is
# imported as server.provision_admin it does not. Adding the directory here
# covers both without depending on how the caller invoked it.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    from app import hash_password
    from db import connect, init
except ModuleNotFoundError as exc:  # pragma: no cover - only on a broken checkout
    raise SystemExit(
        f'Could not import the server modules from {_HERE} ({exc}).\n'
        'Run this script from the repository root:\n'
        '    python3 server/provision_admin.py'
    )


def main():
    init()
    email=input('Administrator email: ').strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):
        raise SystemExit('Please enter a valid email address.')
    name=input('Administrator display name: ').strip()[:120]
    if len(name)<2:
        raise SystemExit('Display name must contain at least two characters.')
    password=getpass.getpass('New password (at least 16 characters): ')
    confirm=getpass.getpass('Confirm password: ')
    if len(password)<16:
        raise SystemExit('Choose a password of at least 16 characters.')
    if password!=confirm:
        raise SystemExit('Passwords did not match.')
    conn=connect()
    existing=conn.execute('SELECT id,role FROM users WHERE email=?',(email,)).fetchone()
    if existing and existing['role']!='admin':
        answer=input('This email belongs to a customer. Type PROMOTE to grant administrator access: ').strip()
        if answer!='PROMOTE':
            conn.close()
            raise SystemExit('No account changes made.')
        conn.execute("UPDATE users SET name=?,password_hash=?,role='admin',active=1 WHERE id=?",
                     (name,hash_password(password),existing['id']))
        conn.execute('DELETE FROM sessions WHERE user_id=?',(existing['id'],))
        verb='Promoted account to administrator and revoked prior sessions.'
    elif existing:
        conn.execute("UPDATE users SET name=?,password_hash=?,active=1 WHERE id=?",
                     (name,hash_password(password),existing['id']))
        conn.execute('DELETE FROM sessions WHERE user_id=?',(existing['id'],))
        verb='Updated administrator credentials and revoked prior sessions.'
    else:
        conn.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'admin')",
                     (name,email,hash_password(password)))
        verb='Created administrator account.'
    conn.commit()
    conn.close()
    print(verb)
    print('Open /admin/ and sign in. The password was not stored in source code or printed.')


if __name__=='__main__':
    main()
