import unittest

import identity_annotations


class IdentityAnnotationTests(unittest.TestCase):
    def test_shot_size_buckets(self):
        self.assertEqual(identity_annotations.shot_size(0.2, 0), "close_up")
        self.assertEqual(identity_annotations.shot_size(0.08, 0), "head_and_shoulders")
        self.assertEqual(identity_annotations.shot_size(0.03, 1), "medium")
        self.assertEqual(identity_annotations.shot_size(0.005, 1), "wide_or_full_body")
        self.assertEqual(identity_annotations.shot_size(0.0, 0), "undetermined")
