import json

from ml.src import export_serving_package


def test_cli_exports_package_and_prints_json(monkeypatch, tmp_path, capsys):
    captured = {}

    def fake_export(asset_key, auth_header, output_root=None, include_predictions=True, create_archive=False):
        captured["asset_key"] = asset_key
        captured["auth_header"] = auth_header
        captured["output_root"] = output_root
        captured["include_predictions"] = include_predictions
        captured["create_archive"] = create_archive
        return {
            "package_dir": str(tmp_path / "pkg"),
            "manifest_path": str(tmp_path / "pkg" / "manifest.json"),
            "copied_files": [],
            "manifest": {"asset_key": asset_key},
        }

    monkeypatch.setattr(export_serving_package, "export_package", fake_export)

    exit_code = export_serving_package.main(
        [
            "--asset-key",
            "kr_stock",
            "--output-root",
            str(tmp_path / "out"),
            "--no-predictions",
            "--archive",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured == {
        "asset_key": "kr_stock",
        "auth_header": None,
        "output_root": tmp_path / "out",
        "include_predictions": False,
        "create_archive": True,
    }
    assert payload["package_dir"].endswith("pkg")
