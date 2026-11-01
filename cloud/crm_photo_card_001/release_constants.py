"""CRM photo -> new card by VIN release (CRM-PHOTO-AUTOFILL-001); no private source in this package."""
PREVIEW_TASK = 'CRM-PHOTO-PREFLIGHT-20261101-R2'  # R1 PASS (run 41304959041); R2: fresh storage probe for the install
INSTALL_TASK = 'CRM-PHOTO-INSTALL-20261101'
PACKAGE = 'cloud/crm_photo_card_001'
NEW_MODULES = ('screen_fields.py', 'vin_brand.py', 'photo_card.py')
