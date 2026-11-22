import argparse
import json
import os
from urllib import request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--nickname", required=True)
    args = parser.parse_args()

    password = os.environ.get("CLANWAR_ADMIN_PASSWORD")
    if not password:
        raise RuntimeError("CLANWAR_ADMIN_PASSWORD is required")

    login_request = request.Request(
        f"{args.base_url.rstrip('/')}/api/v1/auth/password-login",
        data=json.dumps(
            {"nickname": args.nickname, "password": password}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(login_request, timeout=10) as response:
        session_cookie = response.headers.get("Set-Cookie", "")
        user = json.load(response)
    required_cookie_flags = ("httponly", "secure", "samesite=lax")
    if not all(
        flag in session_cookie.lower() for flag in required_cookie_flags
    ):
        raise RuntimeError("Password login did not return a secure session cookie")

    print(
        {
            "login": "ok",
            "username": user["username"],
            "nickname": user.get("display_name"),
            "active": user["is_active"],
            "onboarding_required": user["onboarding_required"],
        }
    )


if __name__ == "__main__":
    main()
