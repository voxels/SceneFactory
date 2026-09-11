import unittest

import identity_captions


class IdentityCaptionTests(unittest.TestCase):
    def test_structured_caption_keeps_identity_fields_separate(self):
        record = {
            "body_poses": [{"joints": []}], "face_count": 1, "person_mask": "/mask.png",
            "face_area_fraction": 0.08, "shot_size": "medium",
            "identity_embedding": {"median_distance": 0.5},
        }
        value = identity_captions.structured_caption(record, "A person in a blue shirt outdoors.", "gage_identity")
        self.assertTrue(value["caption"].startswith("gage_identity, a person."))
        self.assertEqual(value["subject_class"], "person")
        self.assertEqual(value["other_person_face_count"], 0)
        self.assertGreaterEqual(value["clean_shot_score"], 0.65)
