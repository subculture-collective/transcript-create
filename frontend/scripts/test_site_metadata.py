"""Run with python3 -m unittest discover -s frontend/scripts -p 'test_*.py'."""

import importlib.util
import json
import shutil
import struct
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

SCRIPT = Path(__file__).with_name("render-site-metadata.py")
SPEC = importlib.util.spec_from_file_location("metadata", SCRIPT)
metadata = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metadata)


class Head(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = {}
        self.feed(source)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "meta":
            key = attrs.get("property", attrs.get("name"))
            if key in self.tags:
                raise AssertionError(f"Duplicate metadata: {key}")
            self.tags[key] = attrs.get("content")


class MetadataTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy(SCRIPT.parents[1] / "index.html", self.root)
        shutil.copy(SCRIPT.parents[1] / "public/social-card.svg", self.root)
        self.profile = self.root / "brand.json"
        self.profile.write_text(json.dumps({"name": 'HasanAra & "friends"', "description": "Search <the> archive"}))
        self.env = {"SITE_PROFILE_PATH": str(self.profile), "FRONTEND_ORIGIN": "https://hasanara.tv"}

    def test_crawler_gets_brand_and_real_png_without_javascript(self):
        metadata.render(self.root, self.env)
        document = (self.root / "index.html").read_text()
        tags = Head(document).tags
        self.assertEqual(tags["og:title"], 'HasanAra & "friends"')
        self.assertEqual(tags["og:description"], "Search <the> archive")
        self.assertEqual(tags["og:url"], "https://hasanara.tv/")
        self.assertEqual(tags["og:image"], "https://hasanara.tv/social-preview.png")
        self.assertEqual(tags["twitter:image"], tags["og:image"])
        self.assertNotIn("<the>", document)
        png = (self.root / "social-preview.png").read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", png[16:24]), (1200, 630))
        metadata.render(self.root, self.env)
        self.assertEqual((self.root / "index.html").read_text(), document)

    def test_client_artwork_and_explicit_identity_override(self):
        (self.root / "branding").mkdir()
        shutil.copy(self.root / "social-card.svg", self.root / "branding/card.svg")
        self.profile.write_text(json.dumps({"name": "Other archive", "social_image_url": "/branding/card.svg"}))
        original = (self.root / "branding/card.svg").read_bytes()
        metadata.render(self.root, {**self.env, "SITE_NAME": "HasanAra"})
        self.assertEqual(Head((self.root / "index.html").read_text()).tags["og:title"], "HasanAra")
        self.assertEqual((self.root / "branding/card.svg").read_bytes(), original)

    def test_remote_raster_is_preserved(self):
        self.profile.write_text(json.dumps({"social_image_url": "https://cdn.example/card.png"}))
        metadata.render(self.root, self.env)
        self.assertEqual(Head((self.root / "index.html").read_text()).tags["og:image"], "https://cdn.example/card.png")

    def test_invalid_config_fails_before_replacing_shell(self):
        original = (self.root / "index.html").read_bytes()
        for image in ("/../escape.svg", "https://example.org/card.svg", "/missing.svg"):
            with self.subTest(image=image):
                self.profile.write_text(json.dumps({"social_image_url": image}))
                with self.assertRaises(ValueError):
                    metadata.render(self.root, self.env)
                self.assertEqual((self.root / "index.html").read_bytes(), original)
        with self.assertRaises(ValueError):
            metadata.render(self.root, {"SITE_PROFILE_PATH": str(self.profile)})


if __name__ == "__main__":
    unittest.main()
