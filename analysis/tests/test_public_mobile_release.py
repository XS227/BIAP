from fastapi.testclient import TestClient

from api_server import app
from release_routes import mobile_release


client = TestClient(app)


def test_public_mobile_release_route_is_registered():
    response = client.get("/app/release")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == mobile_release()["version"]

    apk_response = client.get("/app/latest.apk")
    assert apk_response.status_code in {200, 404}
    if apk_response.status_code == 404:
        assert apk_response.json()["detail"] == "Latest BIAP APK is not published on this server yet"

    expo_response = client.get("/app/expo.apk")
    assert expo_response.status_code in {200, 404}
    if expo_response.status_code == 404:
        assert expo_response.json()["detail"] == "Latest BIAP Expo/EAS APK is not published on this server yet"

    downloads = client.get("/app/downloads")
    assert downloads.status_code == 200
    assert "APK مستقیم" in downloads.text
    assert "Expo / EAS" in downloads.text


def test_public_mobile_release_matches_manifest():
    release = mobile_release()
    assert release["version"] != "unknown"
    assert isinstance(release["changes"], list) and release["changes"]
    assert release["apkUrl"] == "/app/latest.apk"
    assert isinstance(release["apkAvailable"], bool)
    assert release["expoApkUrl"] == "/app/expo.apk"
    assert isinstance(release["expoApkAvailable"], bool)
    assert release["downloadsUrl"] == "/app/downloads"
