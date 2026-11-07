"""Securely create or promote an administrator account for this development app."""
import getpass
import re
from app import hash_password
from db import connect, init


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
