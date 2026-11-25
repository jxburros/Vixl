"""Score a session's preview with the craft rubric of ``evals.judge`` (hierarchy, spacing, type, colour, motif,
finish; 1-5 each), using any provider the lab supports. The judge sees only the image and the brief, never which arm
made it. A model judging its own work tends to be generous; use a different model as the judge where you can."""

import base64

from evals.judge import SYSTEM, JudgeError, parse, rubric_text

from .providers import ProviderError


def judge_session(chat_factory, config, brief, png):
    try:
        chat = chat_factory(config)
        chat.start(SYSTEM, [])
        chat.add_user([
            {"type": "image", "media_type": "image/png", "data": base64.b64encode(png).decode("ascii")},
            {"type": "text", "text": f"The brief the designer was given:\n{brief}\n\nRubric (1-5 each):\n"
                                     f"{rubric_text()}\n\nScore the design in the image."},
        ])
        scores, notes = parse(chat.step().text)
    except (JudgeError, ProviderError) as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - a failed judgment is recorded, not raised
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {"scores": scores, "mean": round(sum(scores.values()) / len(scores), 2), "notes": notes}
