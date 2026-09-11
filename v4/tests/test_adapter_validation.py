import unittest
from pathlib import Path

import adapter_validation


class AdapterValidationTests(unittest.TestCase):
    def test_first_flux_checkpoint_has_paired_ranked_tensors(self):
        path = Path(__file__).parents[1] / "examples/modeling_interview/build/training/image_identity/experiments/rank8_lr0.0001_steps300/checkpoint-100/pytorch_lora_weights.safetensors"
        if not path.is_file():
            self.skipTest("first FLUX checkpoint has not been emitted yet")
        report = adapter_validation.validate(path, expected_rank=8)
        self.assertEqual(report["status"], "structurally_loadable")
        self.assertEqual(report["paired_module_count"], 60)
        self.assertEqual(report["ranks"], [8])

    def test_all_completed_experiment_adapters_are_structurally_loadable(self):
        root = Path(__file__).parents[1] / "examples/modeling_interview/build/training/image_identity/experiments"
        expected = {
            "rank8_lr0.0001_steps300": 8,
            "rank16_lr0.0001_steps500": 16,
            "rank16_lr5e-05_steps700": 16,
        }
        for experiment, rank in expected.items():
            path = root / experiment / "pytorch_lora_weights.safetensors"
            self.assertTrue(path.is_file(), experiment)
            report = adapter_validation.validate(path, expected_rank=rank)
            self.assertEqual(report["status"], "structurally_loadable")
            self.assertEqual(report["ranks"], [rank])
            self.assertEqual(report["paired_module_count"], 60)


if __name__ == "__main__":
    unittest.main()
