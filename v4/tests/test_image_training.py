import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import identity_pipeline
import image_training


class ImageTrainingTests(unittest.TestCase):
    def test_training_environment_is_offline_only(self):
        with mock.patch.dict("os.environ", {
            "HF_HUB_OFFLINE": "0", "TRANSFORMERS_OFFLINE": "0", "DIFFUSERS_OFFLINE": "0",
        }, clear=False):
            environment = image_training._training_environment()
        self.assertEqual(environment["HF_HUB_OFFLINE"], "1")
        self.assertEqual(environment["TRANSFORMERS_OFFLINE"], "1")
        self.assertEqual(environment["DIFFUSERS_OFFLINE"], "1")

    def test_prepare_exports_hf_metadata_and_official_trainer_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            build = project / "build/identity"
            build.mkdir(parents=True)
            (project / "identity.json").write_text(json.dumps({
                "identity": {"id": "subject", "trigger_token": "subject_identity", "consent": {"status": "verified"}}
            }))
            selections = []
            for index, split in enumerate(("train", "validation", "calibration", "final_test")):
                source = project / f"source-{index}.jpg"
                source.write_bytes(f"image-{index}".encode())
                selections.append({
                    "asset_id": f"asset-{index}", "path": str(source),
                    "sha256": identity_pipeline.sha256_file(source), "group_id": f"group-{index}",
                    "split": split, "eligible_for_export": True, "modality": "portrait_photography",
                    "provenance": "user_supplied_source", "caption": {"caption": "subject_identity, a person"},
                    "annotation": {"person_mask": "/mask.png", "shot_size": "medium", "viewpoint": "frontal"},
                })
            selection_path = build / "selection_manifest.json"
            selection_path.write_text(json.dumps({"identity_id": "subject", "selections": selections}))
            plan = image_training.prepare(project)
            self.assertEqual(plan["dataset"]["counts"], {"train": 1, "validation": 1, "calibration": 1, "final_test": 1})
            command = plan["experiments"][0]["command"]
            self.assertIn("train_dreambooth_lora_flux2_klein.py", " ".join(command))
            self.assertIn("--resume_from_checkpoint", command)
            self.assertIn("--caption_dropout", command)
            metadata = (project / "build/training/image_identity/dataset/train/metadata.jsonl").read_text()
            self.assertIn("subject_identity", metadata)


if __name__ == "__main__":
    unittest.main()
