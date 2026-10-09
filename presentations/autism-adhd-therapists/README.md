# Therapists who help people with autism and ADHD: presentation series

Six slide decks made with Vixl 0.24.0 (the latest release, installed from the release wheel). Each deck
folder in `decks/` holds:

| File | Use |
| --- | --- |
| `*.pptx` | Editable PowerPoint/Keynote/Google Slides deck with speaker notes |
| `*.pdf` | Vector PDF with embedded fonts, for sharing and printing |
| `*.html` | Self-contained browser presentation with a speaker view (press `S`). Speaker notes are included in the file |
| `*.vixl` | Editable Vixl master |
| `*-overview.png` | Contact sheet of every slide |
| `check.json` | Result of `vixl check --checks deck` (all six pass) |

| Deck | Slides | Topic |
| --- | --- | --- |
| [01 Who Helps? The Autism & ADHD Care Team](decks/01-care-team) | 8 | Overview of the professionals, how care unfolds, what good care looks like |
| [02 Occupational Therapy](decks/02-occupational-therapy) | 7 | Sensory processing, motor skills, daily living, executive-function supports |
| [03 Speech-Language Therapy & Communication](decks/03-speech-language-therapy) | 7 | Language, social communication, AAC, ADHD and language, support at home |
| [04 ADHD: Therapy, Coaching & Skills](decks/04-adhd-therapy-and-coaching) | 7 | Parent training, CBT, coaching, school plans, myths and facts |
| [05 Finding the Right Therapist](decks/05-finding-the-right-therapist) | 8 | Path to services, free school help, credentials, questions, green and red flags |
| [06 Therapy for Autistic & ADHD Adults](decks/06-therapy-for-adults) | 6 | Late diagnosis, burnout and masking, adult therapy options, getting started |

The decks use neurodiversity-affirming language and avoid the puzzle-piece symbol. Slides stay short
(under 60 words each) and every slide has speaker notes with the detail. Statistics are U.S. figures from
the CDC and are cited on the slides. The decks are educational and are not medical advice.

## Fonts

Headings use Fraunces and body text uses Lexend, both free under the SIL Open Font License. The PDF and HTML
files embed them. PowerPoint files reference them by name, so install both from Google Fonts on the
presenting computer.

## Rebuilding

```bash
pip install vixl_engine-0.24.0-py3-none-any.whl   # from the v0.24.0 release
python build.py                                   # all decks; --only 03-speech-language-therapy for one
```

`content.py` holds the copy and speaker notes, and `build.py` holds the slide templates. The build installs
the fonts (network access needed) and writes everything into `decks/`.

## Credits

The icons are VIXL Line emoji, adapted from OpenMoji, licensed CC BY-SA 4.0.
