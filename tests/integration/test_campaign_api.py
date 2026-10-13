from tests.integration.test_auth_api import register_and_login


async def test_master_invite_revoke_and_campaign_isolation(api_client):
    master = await register_and_login(api_client, "master")
    player = await register_and_login(api_client, "player")
    outsider = await register_and_login(api_client, "outsider")
    headers = {"Authorization": "Bearer " + master["access_token"]}
    created = await api_client.post(
        "/api/v1/campaigns/", json={"name": "Campaign"}, headers=headers
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    invite_path = f"/api/v1/campaigns/{campaign_id}/invite"
    read = await api_client.get(invite_path, headers=headers)
    assert read.status_code == 200
    invite_code = read.json()["invite_code"]
    assert invite_code
    player_headers = {"Authorization": "Bearer " + player["access_token"]}
    joined = await api_client.post(
        "/api/v1/campaigns/join",
        json={"invite_code": invite_code},
        headers=player_headers,
    )
    assert joined.status_code == 201, joined.text
    assert (
        await api_client.get(invite_path, headers=player_headers)
    ).status_code == 403
    outsider_headers = {"Authorization": "Bearer " + outsider["access_token"]}
    assert (
        await api_client.get(invite_path, headers=outsider_headers)
    ).status_code == 404
    response = await api_client.get(
        f"/api/v1/campaigns/{campaign_id}", headers=outsider_headers
    )
    assert response.status_code == 404
    response = await api_client.get("/api/v1/campaigns/", headers=outsider_headers)
    assert response.status_code == 200
    assert response.json() == []
    revoked = await api_client.post(invite_path + "/revoke", headers=headers)
    assert revoked.status_code == 204
    read = await api_client.get(invite_path, headers=headers)
    assert read.status_code == 200
    assert read.json() == {"invite_code": None}
