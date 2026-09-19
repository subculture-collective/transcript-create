"""Verify the exact patched artifact before accepting its narrow VEX statement."""

from __future__ import annotations

import hashlib
import importlib
from importlib.metadata import PackageNotFoundError, distribution

SOURCES = {
    "lightning": ("lightning.pytorch", "da958b64ddedb2d589ac729df25dce647dbb395e6ed604948bd7b7e1b69a76b0"),
    "pytorch-lightning": ("pytorch_lightning", "2ccf5ae904f3ee8b04e7e2d716f066a7d7da4f10b8e6db94055543c757f74619"),
}


def main() -> None:
    for name, (module_name, expected_hash) in SOURCES.items():
        try:
            package = distribution(name)
        except PackageNotFoundError:
            continue
        if package.version != "2.6.6":
            raise SystemExit(f"VEX qualification requires {name}==2.6.6, found {package.version}")
        source = package.locate_file(module_name.replace(".", "/") + "/core/saving.py")
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected_hash:
            raise SystemExit(f"VEX qualification source hash differs: {name}")
        module = importlib.import_module(module_name)
        saving = importlib.import_module(module_name + ".core.saving")
        try:
            saving._load_state(
                module.LightningModule,
                {"hyper_parameters": {"_instantiator": "hasanara_untrusted_checkpoint.create"}, "state_dict": {}},
            )
        except ValueError as error:
            if "blocked to prevent arbitrary code execution" not in str(error):
                raise
        else:
            raise SystemExit(f"Untrusted checkpoint was not rejected: {name}")
        print(f"Verified patched checkpoint loader: {name}==2.6.6 ({expected_hash})")


if __name__ == "__main__":
    main()
