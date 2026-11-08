import argparse
import getpass
import re
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

from app.core.database import get_session_factory
from app.schemas import Credentials
from app.services.accounts import register


def main() -> None:
    parser = argparse.ArgumentParser(description="NodePass local administration")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-env", help="Generate a local .env without overwriting existing files")
    commands.add_parser(
        "init-credentials-key", help="Append a missing credential key to local .env"
    )
    create = commands.add_parser("create-admin", help="Explicitly create an administrator")
    create.add_argument("email")
    args = parser.parse_args()

    if args.command == "init-env":
        template = Path(".env.example").read_text()
        with Path(".env").open("x", encoding="utf-8") as output:
            output.write(
                template.replace(
                    "replace-with-generated-secret", secrets.token_urlsafe(48)
                ).replace(
                    "replace-with-generated-credentials-key", Fernet.generate_key().decode("ascii")
                )
            )
        print("Created .env with a random session secret. Keep this file private.")
        return

    if args.command == "init-credentials-key":
        path = Path(".env")
        text = path.read_text()
        if re.search(r"(?m)^\s*(?:export\s+)?NODEPASS_CREDENTIALS_KEY\s*=", text):
            parser.error("Credential key already exists; keep it to decrypt existing credentials")
        with path.open("a", encoding="utf-8") as output:
            output.write(f"\nNODEPASS_CREDENTIALS_KEY={Fernet.generate_key().decode('ascii')}\n")
        print("Added credential key to .env. Restart the backend. Back up this key privately.")
        return

    password = getpass.getpass("Password (8-128 characters): ")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    credentials = Credentials(email=args.email, password=password)
    with get_session_factory()() as session:
        user = register(session, credentials, is_admin=True)
        print(f"Created administrator: {user.email}")


if __name__ == "__main__":
    main()
