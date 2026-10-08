"""Operations that finish and organize a design: looks, radial repeat, scatter and document style tags.

One hub keeps the shared dispatcher, schema and CLI compiler to a single hook each.
"""

from . import looks, scatter, styles, symmetry

TYPES = symmetry.TYPES + looks.TYPES + styles.TYPES + scatter.TYPES


def schemas(add):
    symmetry.schemas(add)
    looks.schemas(add)
    styles.schemas(add)
    scatter.schemas(add)


def execute(project, op):
    module = {"radial-repeat": symmetry, "look": looks, "style-set": styles}.get(op["type"], scatter)
    module.execute(project, op)


def compile_command(cmd, args):
    for module in (symmetry, looks, styles, scatter):
        result = module.compile_command(cmd, args)
        if result is not None:
            return result
    return None
