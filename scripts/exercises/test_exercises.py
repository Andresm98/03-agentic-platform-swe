import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import exercises as ex  # noqa: E402


class ExerciseRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base)
        shutil.copytree(ex.EXERCISES / "_ejemplo", self.base / "_ejemplo")

    def add(self, name: str) -> Path:
        folder = self.base / name
        shutil.copytree(self.base / "_ejemplo", folder)
        self.replace(folder / "exercise.yaml", "tu-usuario-de-github", "ana")
        return folder

    @staticmethod
    def replace(path: Path, old: str, new: str) -> None:
        path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    def assert_rejected(self, fragment: str) -> None:
        with self.assertRaises(ex.ExerciseError) as caught:
            ex.validate_all(self.base)
        self.assertIn(fragment, str(caught.exception))

    def test_template_and_copy_are_valid(self) -> None:
        self.add("ana-perez")
        ex.validate_all(self.base)

    def test_template_does_not_count_for_limit(self) -> None:
        for name in ("aa", "bb", "cc"):
            self.add(name)
        ex.validate_all(self.base)

    def test_fourth_exercise_is_rejected(self) -> None:
        for name in ("aa", "bb", "cc", "dd"):
            self.add(name)
        self.assert_rejected("máximo")

    def test_uppercase_name_is_rejected(self) -> None:
        self.add("Ana")
        self.assert_rejected("minúsculas")

    def test_missing_dockerfile_is_rejected(self) -> None:
        (self.add("ana") / "Dockerfile").unlink()
        self.assert_rejected("falta Dockerfile")

    def test_root_user_is_rejected(self) -> None:
        self.replace(self.add("ana") / "Dockerfile", "USER 10001:10001", "USER 0")
        self.assert_rejected("USER")

    def test_named_user_is_rejected(self) -> None:
        self.replace(self.add("ana") / "Dockerfile", "USER 10001:10001", "USER app")
        self.assert_rejected("USER")

    def test_latest_base_image_is_rejected(self) -> None:
        (self.add("ana") / "Dockerfile").write_text(
            "FROM python:latest\nUSER 10001\n", encoding="utf-8"
        )
        self.assert_rejected("versión")

    def test_extra_config_key_is_rejected(self) -> None:
        with (self.add("ana") / "exercise.yaml").open("a", encoding="utf-8") as config:
            config.write("privileged: true\n")
        self.assert_rejected("no permitida")

    def test_privileged_port_is_rejected(self) -> None:
        self.replace(self.add("ana") / "exercise.yaml", "port: 8000", "port: 80")
        self.assert_rejected("port")

    def test_secret_file_is_rejected(self) -> None:
        (self.add("ana") / ".env").write_text("A=1", encoding="utf-8")
        self.assert_rejected("no permitido")

    def test_scope_accepts_one_folder(self) -> None:
        ex.enforce_scope(["exercises/ana/Dockerfile", "exercises/ana/src/main.py"])

    def test_scope_rejects_workflow_change(self) -> None:
        with self.assertRaises(ex.ExerciseError):
            ex.enforce_scope(["exercises/ana/Dockerfile", ".github/workflows/exercises.yml"])

    def test_scope_rejects_two_folders(self) -> None:
        with self.assertRaises(ex.ExerciseError):
            ex.enforce_scope(["exercises/ana/Dockerfile", "exercises/luis/Dockerfile"])

    def test_scope_rejects_template_change(self) -> None:
        with self.assertRaises(ex.ExerciseError):
            ex.enforce_scope(["exercises/_ejemplo/Dockerfile"])

    def test_scope_rejects_shared_readme(self) -> None:
        with self.assertRaises(ex.ExerciseError):
            ex.enforce_scope(["exercises/README.md"])

    def test_render_has_no_egress_and_fixed_resources(self) -> None:
        values = ex.render_values("ana", "a" * 40, 8000)
        self.assertIn(f"tag: ana-{'a' * 40}", values)
        self.assertIn("path: /s/ana", values)
        self.assertIn("otlp: false", values)
        self.assertIn("cpu: 100m", values)

    def test_render_rejects_bad_sha(self) -> None:
        with self.assertRaises(ex.ExerciseError):
            ex.render_values("ana", "main", 8000)


if __name__ == "__main__":
    unittest.main()
