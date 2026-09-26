"""Run Skill Training from one command-line entry point."""

from __future__ import annotations

import argparse
from importlib import import_module

COMMANDS = {
    "prepare": ("s0_prepare_data", "Extract text and split it into episodes"),
    "diffuse": ("s1_diffuse", "Build story outlines from human scripts"),
    "forward": ("s2_forward", "Reconstruct scripts using the skill library"),
    "loss": ("s3_loss", "Compare reconstructions with human scripts"),
    "backward": ("s4_backward", "Update the skill library from feedback"),
    "train": ("s5_train", "Run or resume the complete training loop"),
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m skilltrain",
        description="Skill Training: learn a skill library without updating model weights.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Commands:\n" + "\n".join(
            f"  {name:10} {description}" for name, (_, description) in COMMANDS.items()
        ) + "\n\nRun python -m skilltrain <command> --help for stage options.",
    )
    parser.add_argument("command", choices=COMMANDS, nargs="?", help="workflow to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return
    module_name, _ = COMMANDS[args.command]
    module = import_module(f".workflows.{module_name}", package="skilltrain")
    module.main(args.args)


if __name__ == "__main__":
    main()
