from api_server import app
from release_routes import mobile_release


def test_public_mobile_release_route_is_registered():
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/app/release" in paths
    assert "/app/latest.apk" in paths


def test_public_mobile_release_matches_manifest():
    release = mobile_release()
    assert release["version"] != "unknown"
    assert isinstance(release["changes"], list) and release["changes"]
    assert release["apkUrl"] == "/app/latest.apk"
    assert isinstance(release["apkAvailable"], bool)
