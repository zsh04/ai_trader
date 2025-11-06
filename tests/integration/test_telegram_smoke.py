def _tg_update(text: str):
    return {
        "update_id": 3001,
        "message": {
            "message_id": 333,
            "from": {"id": 999, "is_bot": False, "first_name": "Test"},
            "chat": {"id": 7, "type": "private"},
            "date": 1700000002,
            "text": text,
        },
    }


def test_webhook_endpoint_exists(client):
    r = client.post(
        "/telegram/webhook",
        json={
            "update_id": 1001,
            "message": {
                "message_id": 111,
                "from": {"id": 999, "is_bot": False, "first_name": "Test"},
                "chat": {"id": 42, "type": "private"},
                "date": 1700000000,
                "text": "/ping",
            },
        },
    )
    assert r.status_code == 200
    assert "ok" in r.json()
