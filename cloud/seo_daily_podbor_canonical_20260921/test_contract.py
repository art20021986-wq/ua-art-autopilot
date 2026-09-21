from pathlib import Path
root=Path(__file__).resolve().parent
r=(root/"remote_installer.py").read_text()
c=(root/"controller.py").read_text()
assert "/home/Carix/video/podbor.html" in r
assert "https://www.uaart.com.ua/video/podbor.html" in r
assert "SANDBOX_NONCANONICAL_DRIFT" in r and "PREIMAGE_CHANGED" in r
assert "/home/Carix/crm.db" not in r+c
assert "UAART_BACKUP_MANIFEST_SHA256" in c
assert "live_check()" in c
print("PASS")
