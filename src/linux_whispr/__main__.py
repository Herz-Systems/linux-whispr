"""Entry point: python -m linux_whispr"""

from __future__ import annotations

import argparse
import logging
import sys

from linux_whispr import __version__
from linux_whispr.constants import CONFIG_DIR, DATA_DIR, LOG_FORMAT, MODELS_DIR


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler if available."""
    level = logging.DEBUG if verbose else logging.INFO

    try:
        from rich.logging import RichHandler

        logging.basicConfig(
            level=level,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(rich_tracebacks=True)],
        )
    except ImportError:
        logging.basicConfig(level=level, format=LOG_FORMAT)


def ensure_directories() -> None:
    """Create application directories if they don't exist."""
    for d in [CONFIG_DIR, DATA_DIR, MODELS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="linux-whispr",
        description="Privacy-first voice dictation for Linux",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--version", action="version", version=f"linux-whispr {__version__}")
    parser.add_argument("--config", type=str, default=None, help="Path to config file")
    parser.add_argument("--no-tray", action="store_true", help="Run without system tray icon")
    parser.add_argument("--setup", action="store_true", help="Re-run the first-time setup wizard")
    parser.add_argument(
        "--list-devices", action="store_true", help="List audio input devices and exit"
    )
    parser.add_argument(
        "--list-models", action="store_true", help="List available Whisper models and exit"
    )
    return parser.parse_args()


def cmd_list_devices() -> None:
    """Print available audio input devices and exit."""
    try:
        from linux_whispr.audio.devices import list_input_devices

        devices = list_input_devices()
        if not devices:
            print("No audio input devices found.")
            return
        for dev in devices:
            marker = " *" if dev.is_default else ""
            print(f"  [{dev.index}] {dev.name} ({dev.channels}ch){marker}")
    except OSError as e:
        print(f"Error: {e}")


def cmd_list_models() -> None:
    """Print available Whisper models and their download status."""
    from linux_whispr.stt.model_manager import ModelManager

    mm = ModelManager()
    for m in mm.list_models():
        status = "✓ downloaded" if m.downloaded else "  not downloaded"
        print(f"  {m.name:<20} ~{m.size_mb:>5}MB  {status}")


def main() -> None:
    """Main entry point."""
    args = parse_args()
    setup_logging(verbose=args.verbose)
    ensure_directories()

    logger = logging.getLogger("linux_whispr")

    # Handle info commands that exit immediately
    if args.list_devices:
        cmd_list_devices()
        return

    if args.list_models:
        cmd_list_models()
        return

    logger.info("LinuxWhispr v%s starting...", __version__)

    from pathlib import Path

    from linux_whispr.config import AppConfig
    from linux_whispr.web.server import set_config_path

    config_path = Path(args.config) if args.config else None
    set_config_path(config_path)
    config = AppConfig.load(config_path)

    # The setup wizard is explicit so a normal first launch always starts the
    # dictation engine and dashboard together.
    if args.setup:
        logger.info("Running setup wizard...")
        from linux_whispr.events import event_bus
        from linux_whispr.ui.wizard import SetupWizard

        wizard = SetupWizard(config=config, event_bus=event_bus)
        wizard.run()
        # Config is saved by the wizard; reload in case wizard modified it.
        config = AppConfig.load(config_path)
    elif config.first_run:
        logger.info("Starting without the setup wizard. Run with --setup to configure LinuxWhispr.")

    # Create and setup application
    from linux_whispr.app import LinuxWhispr

    app = LinuxWhispr(config=config, enable_tray=not args.no_tray)

    try:
        app.setup()
        app.start()

        logger.info("LinuxWhispr is running. Press Ctrl+C to stop.")
        _run_main_loop(logger)

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)
    finally:
        app.stop()


def _run_main_loop(logger: logging.Logger) -> None:
    """Run the Qt event loop that drives the native tray and overlay."""
    from linux_whispr.ui.desktop import run_desktop_loop

    logger.debug("Starting Qt desktop event loop")
    run_desktop_loop()


if __name__ == "__main__":
    main()
