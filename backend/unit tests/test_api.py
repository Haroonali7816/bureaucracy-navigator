# End to end API integration test

def test_signup_login_and_list_letters_flow(client):
    # 1. Signing up should return a usable JWT immediately -- per main.py, signup logs
    #    you in automatically, no separate "confirm your email" step in this project.
    signup_response = client.post(
        "/auth/signup",
        json={"email": "amara@example.com", "password": "correct-horse-battery-staple"},
    )
    assert signup_response.status_code == 200
    signup_token = signup_response.json()["access_token"]
    assert signup_token

    # 2. A brand-new user has no letters yet.
    letters_response = client.get(
        "/letters", headers={"Authorization": f"Bearer {signup_token}"}
    )
    assert letters_response.status_code == 200
    assert letters_response.json() == []

    # 3. Signing up again with the same email must be rejected
    duplicate_response = client.post(
        "/auth/signup",
        json={"email": "amara@example.com", "password": "a-different-password"},
    )
    assert duplicate_response.status_code == 400

    # 4. Logging in with the original credentials works.
    login_response = client.post(
        "/auth/login",
        data={"username": "amara@example.com", "password": "correct-horse-battery-staple"},
    )
    assert login_response.status_code == 200
    login_token = login_response.json()["access_token"]

    # 5. The login token works too, and sees the same (still-empty) letter list.
    letters_again = client.get(
        "/letters", headers={"Authorization": f"Bearer {login_token}"}
    )
    assert letters_again.status_code == 200
    assert letters_again.json() == []

    # 6. No token at all must be rejected outright .
    unauthenticated_response = client.get("/letters")
    assert unauthenticated_response.status_code == 401