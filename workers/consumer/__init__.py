"""Container-friendly entrypoint for the order consumer worker."""

from scripts.order_consumer import main as _run


def run() -> None:
    """Run the order consumer using the existing script entrypoint."""
    _run()


__all__ = ["run"]
