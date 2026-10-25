"""An optional rubric judge for the craft tasks: look at the delivered document and score it 1-5.

The deterministic ``craft`` check of ``harness.grade`` counts what the composition checks can measure. This judge
adds what they cannot: a model looks at the document rendered at delivery size and scores it against the rubric of
the craft re-judging (hierarchy, spacing, type, colour, motif, finish). It is off by default, never runs in CI or in
the test suite (tests give it a scripted client), costs one model call per craft task, and is not part of the stored
baseline: a judge's score moves with the judge. Turn it on with ``python -m evals.run --judge``; the endpoint is
configurable (``--judge-endpoint`` or ``VIXL_JUDGE_ENDPOINT``), any server that speaks the Anthropic Messages API.
"""

import base64
import io
import json
from pathlib import Path
import re

from PIL import Image

# The six sub-scores of the re-judging kit, each 1-5, with what a 1, a 3 and a 5 look like.
RUBRIC = {
    "hierarchy": "Does one element read first, then a clear second and third? 1: everything the same weight or two rivals; "
                 "3: a leader, but the order after it is unclear; 5: the eye goes straight to one thing and the rest steps down.",
    "spacing": "Are gaps, margins and alignments deliberate? 1: ragged edges, holes and crowding; 3: mostly even with a "
               "few stray gaps; 5: one margin, one rhythm, space grouped by meaning.",
    "type": "Are size, weight and face used with intent? 1: one size and weight, or clashing faces; 3: steps exist but "
            "blur; 5: a clear scale, weights that carry meaning, comfortable line lengths.",
    "colour": "Is the palette restrained and doing a job? 1: clashing or muddy, or one flat colour; 3: pleasant but "
              "unfocused; 5: few colours, the accent used on what matters, strong contrast where it is needed.",
    "motif": "Is the imagery or ornament specific to the brief? 1: a generic stand-in, or none where the brief needs "
             "one; 3: relevant but plain; 5: specific, well drawn and tied to the subject.",
    "finish": "Does it read as finished, not merely correct? 1: placeholder look, flat default styling; 3: tidy but "
              "bare; 5: polished details, nothing left over, nothing missing.",
}
SYSTEM = ("You are a strict senior graphic designer judging a finished design from one image. Score each rubric "
          "dimension from 1 to 5 with whole numbers, judging only what you see. Reply with one JSON object and "
          "nothing else: {\"scores\": {\"hierarchy\": n, \"spacing\": n, \"type\": n, \"colour\": n, \"motif\": n, "
          "\"finish\": n}, \"notes\": \"two sentences on the weakest dimension\"}.")
MAX_SIDE = 1568  # Longest side of the image sent: delivery size for most briefs, reduced for a print-size page.
ENDPOINT_ENV = "VIXL_JUDGE_ENDPOINT"


class JudgeError(RuntimeError):
    """The judge could not score a document: no document, an unreadable reply or a failed call."""


def rubric_text():
    return "\n".join(f"- {name}: {text}" for name, text in RUBRIC.items())


def prompt(task):
    return (f"The brief the designer was given:\n{task['prompt']}\n\nRubric (1-5 each):\n{rubric_text()}\n\n"
            "Score the design in the image.")


def deliverable(task, workspace):
    """The task's document rendered at delivery size, as PNG bytes."""
    from vixl import Project

    workspace = Path(workspace)
    name = task.get("document")
    path = workspace / name if name else next(iter(sorted(workspace.glob("*.vixl"))), None)
    if path is None or not path.is_file():
        raise JudgeError("the task left no .vixl document to judge")
    image = Project.load(path).render().convert("RGB")
    if max(image.size) > MAX_SIDE:
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def parse(text):
    """``{dimension: 1-5}`` and the notes from a judge's reply (the first JSON object in it)."""
    match = re.search(r"\{.*\}", text or "", re.S)
    if match is None:
        raise JudgeError(f"the judge's reply has no JSON object: {text[:120]!r}")
    try:
        reply = json.loads(match.group(0))
        scores = reply["scores"]
    except (ValueError, KeyError, TypeError) as exc:
        raise JudgeError(f"the judge's reply is not {{scores, notes}}: {text[:120]!r}") from exc
    if not isinstance(scores, dict) or set(scores) != set(RUBRIC) or not all(
            type(value) is int and 1 <= value <= 5 for value in scores.values()):
        raise JudgeError(f"scores must be whole numbers 1-5 for {', '.join(RUBRIC)}: {scores!r}")
    return scores, str(reply.get("notes", ""))[:600]


class Judge:
    """``Judge(model, endpoint=None, client=None, save=None)``: call it with ``(task, workspace)`` for
    ``{scores, mean, notes, model}`` (or ``{error}``). ``client`` is anything with the Anthropic SDK's
    ``messages.create`` (tests pass a scripted one); without it the SDK client is built, with ``base_url`` set from
    ``endpoint``. ``save`` is a folder that receives each judged image as ``TASK.png``."""

    def __init__(self, model, endpoint=None, client=None, save=None):
        self.model, self.endpoint, self.save = model, endpoint, Path(save) if save else None
        if client is None:
            import anthropic

            client = anthropic.Anthropic(**({"base_url": endpoint} if endpoint else {}))
        self.client = client

    def __call__(self, task, workspace):
        try:
            png = deliverable(task, workspace)
            if self.save is not None:
                self.save.mkdir(parents=True, exist_ok=True)
                (self.save / f"{task['id']}.png").write_bytes(png)
            reply = self.client.messages.create(
                model=self.model, max_tokens=600, system=SYSTEM,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": base64.b64encode(png).decode("ascii")}},
                    {"type": "text", "text": prompt(task)}]}])
            text = "".join(getattr(block, "text", "") for block in reply.content)
            scores, notes = parse(text)
        except JudgeError as exc:
            return {"error": str(exc), "model": self.model}
        except Exception as exc:  # noqa: BLE001 - a failed call must not fail the eval run; it is recorded instead
            return {"error": f"{type(exc).__name__}: {exc}", "model": self.model}
        return {"scores": scores, "mean": round(sum(scores.values()) / len(scores), 2), "notes": notes,
                "model": self.model}
