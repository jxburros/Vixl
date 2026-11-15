"""The structure tree of a tagged PDF (``export(tagged=True)``).

Every piece of page content is either tagged or an artifact. A layer that carries meaning opens one marked-content
sequence with its own MCID and gets one structure element:

- a text layer is ``P``, or ``H1``–``H3`` from its text stage (display and h1 are ``H1``, h2 ``H2``, h3 ``H3``): the
  stage its font follows, else the stage its size reads as. Text drawn as an image (effects, masks …) keeps its
  words in ``/ActualText``;
- a layer with alt text is a ``Figure`` with ``/Alt`` (a described group is one figure, not its parts);
- an image, frame, link, paint or pixel layer without alt is a ``Figure`` without ``/Alt`` (the ``accessibility``
  check reports it); a group drawn as one image is a ``Figure`` whose ``/Alt`` is the text inside it;
- a form field in a fillable PDF is a ``Form`` element that points at its widget (``OBJR``);
- decorative layers, undescribed shapes, solids and gradients, and the page background are ``/Artifact``.

A plain group is transparent: its children are tagged one by one. The tree is ``Document`` > ``Sect`` (one per page)
> elements in the page's reading order (``accessibility reading_order`` first, then top to bottom and left to
right), independent of the drawing order, which the MCIDs follow. The ``ParentTree`` maps each page's MCIDs (by the
page's ``/StructParents``) and each widget (by its ``/StructParent``) back to its element.
"""

import numpy as np

from .pdf_writer import Name, Text

HEADINGS = {"display": "H1", "h1": "H1", "h2": "H2", "h3": "H3"}
ARTIFACT = "/Artifact BMC"


def text_tag(project, layer):
    """``H1``–``H3`` for a heading, else ``P``. The level is the layer's text stage: the stage its font follows
    (``stage: h2`` in a document with a font for it), else the stage its size reads as (``text.is_heading``)."""
    from .type_roles import stage_for_size

    role = layer.get("font_role")
    stage = role if role in HEADINGS else None
    if stage is None and role in (None, "heading"):
        stage = stage_for_size(project, float(layer.get("size", 0)))
    return HEADINGS.get(stage, "P")


def plain_text(layer):
    return " ".join(str(layer.get("text") or "").split())


class Structure:
    """The structure tree of one export; ``page`` opens the tags of each page and ``finish`` writes the root."""

    def __init__(self, writer):
        self.writer = writer
        self.root = writer.reserve()
        self.document = writer.reserve()
        self.sections = []
        self.parents = []  # (ParentTree key, value): a page's [elements by MCID], or a widget's element
        self.next_key = 0

    def key(self):
        self.next_key += 1
        return self.next_key - 1

    def page(self, view, page_ref):
        return PageTags(self, view, page_ref)

    def finish(self):
        """Write the Document element and the StructTreeRoot; returns the root reference for the catalog."""
        writer = self.writer
        writer.add({"Type": Name("StructElem"), "S": Name("Document"), "P": self.root, "K": self.sections},
                   self.document)
        tree = writer.add({"Nums": [part for key, value in sorted(self.parents, key=lambda pair: pair[0])
                                    for part in (key, value)]})
        writer.add({"Type": Name("StructTreeRoot"), "K": self.document, "ParentTree": tree,
                    "ParentTreeNextKey": self.next_key}, self.root)
        return self.root


class PageTags:
    """Marked content and structure elements of one page."""

    def __init__(self, structure, view, page_ref):
        self.structure, self.view, self.page_ref = structure, view, page_ref
        self.key = structure.key()
        self.elements = []  # {tag, id, lineage, box, mcid | widget, alt, actual}
        self.inside = False  # within a tagged sequence: nothing nested is marked
        self.count = 0

    def _add(self, tag, layer, box, lineage=(), **extra):
        element = {"tag": tag, "id": layer["id"] if layer else f"@{len(self.elements)}", "box": box,
                   "lineage": lineage, **extra}
        self.elements.append(element)
        return element

    def _marked(self, tag, layer, box, lineage=(), **extra):
        self._add(tag, layer, box, lineage, mcid=self.count, **extra)
        self.count += 1
        return f"/{tag} <</MCID {self.count - 1}>> BDC"

    def open(self, builder, layer, box, matrix, index, layers):
        """The operator that opens ``layer``'s marked content, or None for a plain group (its children are tagged)."""
        from .accessibility import IMAGE_TYPES, decorative

        kind = layer["type"]
        if layer.get("decorative") or (kind != "text" and decorative(layer)):
            return ARTIFACT
        reason = builder.raster_reason(layer)
        if kind == "group" and reason is None and not layer.get("alt"):
            return None
        lineage = _lineage(layer, index)
        x, y, w, h = box
        corners = (matrix @ np.array([[x, x + w, x, x + w], [y, y, y + h, y + h], [1, 1, 1, 1]], dtype=float))[:2]
        box = (float(corners[0].min()), float(corners[1].min()), float(np.ptp(corners[0])), float(np.ptp(corners[1])))
        if layer.get("alt"):
            return self._marked("Figure", layer, box, lineage, alt=layer["alt"])
        if kind == "text":
            return self._marked(text_tag(self.view, layer), layer, box, lineage, actual=plain_text(layer) if reason else None)
        if kind == "group":
            inner = self._text_of([item for item in layers if layer["id"] in _lineage(item, index)[1:]])
            return self._marked("Figure", layer, box, lineage, alt=inner or None)
        if kind in IMAGE_TYPES:
            return self._marked("Figure", layer, box, lineage)
        if kind == "field" and not getattr(builder, "fillable", False):
            return self._marked("P", layer, box, lineage)
        return ARTIFACT

    @staticmethod
    def _text_of(layers):
        words = [plain_text(item) for item in layers if item["type"] == "text" and item["visible"]]
        return " ".join(word for word in words if word)[:2000]

    def page_figure(self, layers, bounds):
        """The operator for a page drawn as one image: a Figure described by the page's alt, else by its text."""
        from .accessibility import page_alt, reading_order, resolved_text

        canvas = self.view.state["canvas"]
        alt = resolved_text(self.view, page_alt(self.view.state))
        if not alt:
            texts = [item for item in layers if item["type"] == "text" and item["visible"] and item["id"] in bounds]
            alt = self._text_of(reading_order(self.view.state, texts, bounds))
        return self._marked("Figure", None, (0, 0, canvas["width"], canvas["height"]), alt=alt or None)

    def widget(self, box, label):
        """A form widget on this page: returns its ``/StructParent`` key; ``attach`` gives it the annotation."""
        key = self.structure.key()
        self._add("Form", None, box, widget=key, alt=label or None)
        return key

    def attach(self, key, ref):
        next(e for e in self.elements if e.get("widget") == key)["ref"] = ref

    def ordered(self):
        """The elements in reading order: the page's explicit order (a named group places everything in it), then
        top to bottom and left to right."""
        from .accessibility import visual_order

        explicit = (self.view.state.get("page_accessibility") or {}).get("reading_order") or []
        rank = {ident: i for i, ident in enumerate(explicit)}
        bounds = {e["id"]: e["box"] for e in self.elements}
        visual = visual_order(self.elements, bounds)

        def placed(element):
            return min((rank[i] for i in element["lineage"] if i in rank), default=None)

        first = sorted((e for e in visual if placed(e) is not None), key=placed)
        return first + [e for e in visual if placed(e) is None]

    def finish(self):
        """Write this page's Sect and elements; returns the page's ``/StructParents`` key."""
        structure, writer = self.structure, self.structure.writer
        section = writer.reserve()
        by_mcid, kids = {}, []
        for element in self.ordered():
            record = {"Type": Name("StructElem"), "S": Name(element["tag"]), "P": section, "Pg": self.page_ref}
            if element.get("alt"):
                record["Alt"] = Text(element["alt"])
            if element.get("actual"):
                record["ActualText"] = Text(element["actual"])
            if "mcid" in element:
                record["K"] = element["mcid"]
                ref = writer.add(record)
                by_mcid[element["mcid"]] = ref
            else:
                record["K"] = {"Type": Name("OBJR"), "Obj": element["ref"], "Pg": self.page_ref}
                ref = writer.add(record)
                structure.parents.append((element["widget"], ref))
            kids.append(ref)
        writer.add({"Type": Name("StructElem"), "S": Name("Sect"), "P": structure.document, "Pg": self.page_ref,
                    "K": kids}, section)
        structure.sections.append(section)
        structure.parents.append((self.key, [by_mcid[i] for i in range(self.count)]))
        return self.key


def _lineage(layer, index):
    out, cursor = [], layer
    while cursor is not None:
        out.append(cursor["id"])
        cursor = index.get(cursor.get("parent"))
    return out
