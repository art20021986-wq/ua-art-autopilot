import gate_b_controller_v4 as gbc


def test_check_approval_rejects_wrong_token():
    try:
        gbc.check_approval("wrong-token")
        raised = False
    except gbc.GateBBlocked:
        raised = True
    assert raised


def test_check_approval_accepts_exact_token():
    assert gbc.check_approval("CRM-UNIFIED-CATALOG-001-V1.0-APPROVED") is True


def test_extract_json_finds_embedded_object():
    text = "some console noise\n{\"status\": \"INSTALL_PASS\", \"backup_dir\": \"/x\"}\nmore noise"
    parsed = gbc._extract_json(text)
    assert parsed["status"] == "INSTALL_PASS"
    assert parsed["backup_dir"] == "/x"
