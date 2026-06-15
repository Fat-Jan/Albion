"""Lightweight helpers for readable KOOK card sections."""

from khl.card import Element, Module, Types


def kmd_section(title: str, lines: list[str] | tuple[str, ...]) -> Module.Section:
    return Module.Section(Element.Text("\n".join([f"**{title}**", *lines]), Types.Text.KMD))


def interleave_dividers(modules: list) -> list:
    result = []
    for module in modules:
        if result:
            result.append(Module.Divider())
        result.append(module)
    return result
