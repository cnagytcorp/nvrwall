#!/usr/bin/env python
import getpass

from app.tokens import init_db, set_admin_password

if __name__ == "__main__":
    print("Set admin password for NVR wall web admin")
    pwd1 = getpass.getpass("New password: ")
    pwd2 = getpass.getpass("Confirm password: ")

    if pwd1 != pwd2:
        print("Passwords do not match. Aborting.")
        raise SystemExit(1)

    if not pwd1:
        print("Empty password not allowed. Aborting.")
        raise SystemExit(1)

    init_db()
    set_admin_password(pwd1)
    print("Admin password updated successfully.")
