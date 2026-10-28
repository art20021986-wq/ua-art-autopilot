"""CRM button «Фото главной страницы» release (HOME-PHOTO-001); no private source in this package."""
PREVIEW_TASK = 'HOME-PHOTO-PREFLIGHT-20261028-R2'  # R1 refused by the CI contract check (exec in a test), nothing ran
INSTALL_TASK = 'HOME-PHOTO-INSTALL-20261028'
PACKAGE = 'cloud/home_photo_001'
NEW_MODULES = ('ua_home_photo_crop.py', 'ua_home_photo_site.py', 'ua_home_photo_bot.py')
# YOLOX-S car detector of the OpenCV Model Zoo (Apache-2.0), pinned to a commit and a hash.
MODEL = 'ua_home_photo/object_detection_yolox_2022nov.onnx'
MODEL_URL = ('https://media.githubusercontent.com/media/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/'
             'models/object_detection_yolox/object_detection_yolox_2022nov.onnx')
MODEL_SHA256 = 'c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063'
MODEL_BYTES = 35858002
