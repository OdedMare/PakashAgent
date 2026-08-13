"""Load prompt text from the installed package."""

from pkgutil import get_data


def load(name: str) -> str:
    if not name.isidentifier():
        raise ValueError("invalid prompt name")
    content = get_data(__package__, name + ".md")
    if content is None:
        raise FileNotFoundError(name + ".md")
    return content.decode("utf-8")
