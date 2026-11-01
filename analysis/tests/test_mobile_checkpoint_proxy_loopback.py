"""Actual loopback HTTP transport tests for both checkpoint AI proxy adapters.

A local fake proxy is used; this is NOT a live biap-ai-proxy certification.
No production endpoint, API key, financial data or company DB is accessed.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from global_markets.saved_company_ai import call_biap_proxy
from iran_company_view import _call_llm


@pytest.fixture
def local_proxy():
    records = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            size = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(size)
            records.append({
                "path": self.path,
                "headers": dict(self.headers),
                "body": json.loads(payload),
            })
            reply = json.dumps({
                "content": [{"type": "text", "text": "Stored-data explanation only"}]
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("adapter", [call_biap_proxy, _call_llm])
def test_real_loopback_post_to_configured_proxy(monkeypatch, local_proxy, adapter):
    url, records = local_proxy
    monkeypatch.setenv("BIAP_AI_PROXY_URL", url)
    monkeypatch.setenv("BIAP_AI_PROXY_TOKEN", "checkpoint-test-only")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-forwarded")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-forwarded")
    report, model = adapter("SYNTHETIC_STORED_SNAPSHOT_ONLY")
    assert report == "Stored-data explanation only"
    assert model
    assert len(records) == 1
    request = records[0]
    assert request["path"] == "/messages"
    assert request["headers"]["Authorization"] == "Bearer checkpoint-test-only"
    assert request["body"]["messages"] == [
        {"role": "user", "content": "SYNTHETIC_STORED_SNAPSHOT_ONLY"}
    ]
    assert "must-not-be-forwarded" not in json.dumps(request)
