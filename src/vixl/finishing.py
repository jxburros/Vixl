"""Operations that finish and organize a design: looks, radial repeat and document style tags.

One hub keeps the shared dispatcher, schema and CLI compiler to a single hook each.
"""

from . import looks, styles, symmetry

TYPES = symmetry.TYPES + looks.TYPES + styles.TYPES


def schemas(add):
    symmetry.schemas(add)
    looks.schemas(add)
    styles.schemas(add)


def execute(project, op):
    {"radial-repeat": symmetry, "look": looks, "style-set": styles}[op["type"]].execute(project, op)


def compile_command(cmd, args):
    for module in (symmetry, looks, styles):
        result = module.compile_command(cmd, args)
        if result is not None:
            return result
    return None
