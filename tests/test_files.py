import io

def test_files_upload_and_list(app_client):
    content = b"hello world"
    files = {"file": ("hello.txt", io.BytesIO(content), "text/plain")}
    r = app_client.post("/files/upload", files=files)
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    file_id = j["file"]["id"]

    r2 = app_client.get("/files")
    assert r2.status_code == 200
    j2 = r2.json()
    assert any(f["id"] == file_id for f in j2.get("files", []))
