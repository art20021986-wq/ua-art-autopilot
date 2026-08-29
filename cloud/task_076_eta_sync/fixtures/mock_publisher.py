"""In-memory publisher/rebuild adapter for offline tests only."""


class MockPublisher:
    def __init__(self):
        self.fail_video = False
        self.fail_site = False
        self.fail_rebuild_card = False
        self.fail_rebuild_catalogs = False
        self.published_pages = {}
        self.catalogs_rebuilt = 0

    def rebuild_card(self, car_id):
        if self.fail_rebuild_card:
            return False
        self.published_pages[car_id] = "rebuilt"
        return True

    def rebuild_catalogs(self):
        if self.fail_rebuild_catalogs:
            return False
        self.catalogs_rebuilt += 1
        return True

    def publish_video(self, car_id):
        return not self.fail_video

    def publish_site(self, car_id):
        return not self.fail_site
