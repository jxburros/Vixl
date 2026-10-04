# Choosing and Combining Fonts: A Guide for Agents

Vixl's typeface catalog (`vixl fonts`, `vixl font show FAMILY`) lists 104 open-licensed Google Fonts families, every weight and italic checked against the Google Fonts CSS API. The 60 curated pairings (`vixl font pairings`, `vixl font pairing NAME`) say why each one works. Install a pairing with `vixl font pair NAME` (or `random`) and layouts use it. The bundled fallback font is for proofing only. The rules below are meant to be applied mechanically: each one says what to do and what to avoid. Single-family pairings are recorded with `relationship: superfamily`.

## 1. Classification primer

Classification tells you how a typeface is built, and that tells you how it will behave next to another face.

**Serifs.** These follow the Vox-ATypI classification (1954, adopted by ATypI in 1962).
- **Humanist / Garalde (old-style).** Renaissance forms with a diagonal stress and moderate contrast. They feel warm and bookish. Examples: EB Garamond, Crimson Pro, Cardo, Alegreya, Vollkorn, Libre Caslon Text.
- **Transitional (Réale).** 18th-century forms with a near-vertical stress and sharper detail. They feel authoritative and neutral. Examples: Libre Baskerville, Source Serif 4, PT Serif, Newsreader, Merriweather.
- **Didone (modern).** Extreme thick/thin contrast, hairline serifs and a vertical stress. They feel glamorous. Use them large only. Examples: Bodoni Moda, Playfair Display, DM Serif Display, Abril Fatface.
- **Mechanistic (slab).** Low contrast and heavy rectangular serifs. They feel sturdy, retro or friendly. Examples: Roboto Slab, Bitter, Zilla Slab, Arvo, Alfa Slab One.
- **Glyphic.** Carved or inscriptional forms with flared or wedge serifs, often caps-led. They feel monumental. Examples: Cinzel, Marcellus.

**Sans serifs (Lineale).** The British Standard of 1967 split this group into four subclasses.
- **Grotesque.** 19th-century and early 20th-century forms with some stroke contrast and quirks. Examples: Libre Franklin, Archivo, Work Sans, Schibsted Grotesk, Space Grotesk.
- **Neo-grotesque.** Regular, low-contrast and neutral, in the Helvetica tradition. Examples: Inter, Roboto, Geist, Instrument Sans.
- **Geometric.** Built from circles and straight lines. Examples: Montserrat, Poppins, Jost, DM Sans, League Spartan.
- **Humanist.** Based on handwriting, with open apertures and the highest small-size legibility. Examples: Open Sans, Source Sans 3, Fira Sans, Lato, Noto Sans.

**Others.** These are monospace, display (condensed, fat-face, pixel, inline), handwriting and script, and blackletter.

Google Fonts' *font matrix* article, based on Indra Kupferschmid, gives a second way to sort type. It looks at the *skeleton*: dynamic (open, calligraphic), rational (closed, vertical) or geometric (constructed). Pairings work best when the skeletons are either clearly different or clearly the same.

## 2. Pairing principles

1. **Use contrast of classification, not contrast of everything.** A didone headline over a humanist sans body works. Two similar faces, such as two neo-grotesques or Lora with Merriweather, look like a mistake. *Do* pair a geometric sans with a humanist sans, or a serif with a sans. *Don't* pair Inter with Roboto, or Montserrat with Poppins.
2. **Contrast is not mandatory.** Butterick calls "only mix serif with sans" a myth and says lower contrast between fonts can be more effective. Newspapers often use two serifs. A *concord* pair, such as Fredoka with Nunito, needs a clear difference in size and weight so it reads as intentional.
3. **Match x-height and proportions when two faces sit near each other.** Google Fonts describes "sibling" faces as sharing x-height, contrast, width and mood. At the same point size, a small-x-height face next to a large-x-height face looks mis-sized. Examples: Cormorant Garamond with Jost (both small), and Libre Franklin with Libre Baskerville (both large). If they don't match, make the heading clearly larger so the comparison never happens.
4. **Shared construction or era.** Faces from the same skeleton or period harmonize. Examples: Cinzel with EB Garamond (classical), League Gothic with Libre Baskerville (old newspaper), and Space Mono with Space Grotesk (shared DNA).
5. **Superfamilies are the safest pairing.** Families designed together share metrics, so swapping between them never disturbs layout. Examples: Source Serif/Sans/Code, IBM Plex Sans/Serif/Mono, Roboto/Slab/Mono, Noto Sans/Serif/CJK, DM Serif/Sans/Mono, Alegreya/Alegreya Sans, Instrument Serif/Sans, Geist/Geist Mono.
6. **Limit the number of families to two.** Butterick says most documents can take a second font, few a third, and almost none four. Count families, not styles. A third family is allowed only for code (a monospace face).
7. **Give each family one fixed role.** One family for headings and one for body, used the same way everywhere. Never switch the heading face partway through a design.
8. **Use weight contrast.** A pairing needs a visible weight step, usually heading 600–800 over body 400. Two faces at the same weight and similar size blur together. Avoid weights below 300 for anything under about 32px.

## 3. Role assignment

| Role | Choose | Avoid |
|---|---|---|
| **Display** (≥ 40px, a few words) | Didones, fat faces, condensed gothics, expressive grotesques, scripts, blackletter | Text-optimized faces at hairline weights |
| **Heading** (20–40px) | Any family whose `roles` includes `heading`; weight 600–800 | Caps-only faces for long headings (Cinzel, Bebas Neue) |
| **Body/text** (15–20px web, 10–12pt print) | Humanist or neo-grotesque sans, transitional or old-style serifs, screen slabs. Prefer a large or medium x-height | Display, didone, script, condensed, monospace, or `x_height: small` below 18px |
| **UI / labels** (11–14px) | Large-x-height sans with open apertures (Inter, Roboto, Source Sans 3, Fira Sans, IBM Plex Sans, Atkinson Hyperlegible Next) | Geometric faces with closed circles at tiny sizes, old-style figures |
| **Caption** | The body family one step smaller, or a monospace in uppercase with tracking | Light weights |
| **Code** | Monospace only (JetBrains Mono, Fira Code, Source Code Pro, IBM Plex Mono) | Proportional fonts |
| **Numerals** (tables, prices, dashboards) | Faces with tabular lining figures (Inter, Roboto, IBM Plex, Source Sans 3, any monospace) | Raleway or Alegreya-style old-style figures in tables |

Material Design 3 uses five roles: display, headline, title, body and label. Each comes in three sizes, and that is a good default scale. Display styles are for short, important text or numbers.

## 4. Size, weight, leading and measure

- **Scale.** Use a ratio of 1.2–1.333 for dense UI and 1.414–1.618 for editorial and posters. Headings should be at least 1.5× the body size, or be clearly heavier.
- **Leading.** Set body line-height to 120–145% of the font size (Butterick). Use about 1.5 for screen paragraphs. Large-x-height and dark faces (Merriweather, Bitter) need the upper end. Headings take 1.0–1.2, and all-caps condensed display can go as low as 0.9–1.0.
- **Measure.** Aim for 45–90 characters per line (Butterick), with 60–75 as a good target. Wide faces (Montserrat, Lexend, Libre Baskerville) reach the limit sooner.
- **Body size.** Use 15–25px on the web. Small-x-height faces (EB Garamond, Crimson Pro, Spectral, Jost) need 18px or more.
- **Tracking.** Add +5–10% tracking to all-caps labels. Tighten large display headlines slightly. Never letter-space lowercase body text.

## 5. Single-family designs

Use one family when the brief calls for minimal, utilitarian, UI, dashboard or documentation work, or whenever you are unsure. Butterick notes that one font with variations in size, weight, italic and small caps often covers everything. Pick a family with at least 4 weights and italics (`weights` length ≥ 4 and `italic: true`). Examples: Inter, Roboto, IBM Plex Sans, Source Sans 3, Plus Jakarta Sans, Literata, EB Garamond. In `the pairings`, single-family entries use `"relationship": "superfamily"` and have the same family in both `heading` and `body`.

## 6. Display faces, scripts and small sizes

- **Display faces only at large sizes.** Families whose `roles` lack `text` should never be used for paragraphs. Hairline didones (Bodoni Moda, Playfair Display, Cormorant Garamond) break down below about 20–24px. Google's optical-size guidance says small sizes need lower contrast, larger x-heights, wider letters and looser spacing, and display cuts have the opposite traits.
- **Scripts and handwriting never for body.** Use them for one to five words: a logo, a name or an annotation. Never set a script in all caps, because the connecting strokes break. Never use one for buttons or labels.
- **Caps-only faces** (Bebas Neue, Cinzel, Bungee, Monoton): their `x_height` value is nominal. Use them for short uppercase headings.
- **Thumbnails and social images.** If an image may be shown at 10–25% of its size, the headline must be heavy (700+) and simple, with low contrast and a large x-height. Anton, Bebas Neue, Archivo Black, Inter 800 and Montserrat 800 work. Avoid didone hairlines, thin weights, scripts and blackletter. Keep minor text at 24px or more on a 1080px canvas.
- **Contrast with the background.** Thin and light weights lose contrast first. Use weight 400 or more for text on images or colored backgrounds.

## 7. Multilingual coverage

Before you pick a family, check that it covers the script you need. Most catalog families cover Latin, and many also cover Cyrillic and Greek. For CJK, Arabic or Indic text, use the matching Noto family (Noto Sans JP/SC, Noto Serif JP, Noto Sans Arabic, Noto Sans Devanagari) and pair it with Noto Sans or Noto Serif for Latin. Noto was built to share one design voice across scripts. When the language is unknown or user-generated, default to Noto Sans with Noto Serif. CJK fonts are large, so load only the weights you need. A script that silently falls back to a system font is worse than a plain but consistent family.

## 8. When choosing at random

Random generation should limit itself to choices that keep a design coherent.

1. **Pick the pairing first.** Sample from `the pairings` filtered by mood or `best_for`. Don't pick two families independently. If you must build a new pair, choose the body face first (it needs `text` in `roles`, a medium or large x-height and at least 3 weights). Then choose a heading face with a *different* `classification`, or the same superfamily. Reject the pair if both share a classification, if both are display faces, or if both have small x-heights on a UI.
2. **Use only verified weights.** Choose weights from the font's `weights` list. Heading weight should normally be at least body weight + 200. Exceptions are single-weight display faces and size-driven scales such as Material's Roboto 500/400.
3. **Make everything else follow the pairing's mood.** Use the pairing's `mood` tags to pick the palette and layout. Luxury or elegant: muted or monochrome colors, generous whitespace. Bold-poster or brutalist: high contrast, tight grids. Playful: saturated colors and rounded shapes. Academic or editorial: restrained colors and a strict column measure.
4. **Respect the `avoid` and `caution` fields.** Treat them as hard rules. For example, no Great Vibes in caps and no Bebas Neue paragraphs.
5. **Cap the family count** at two, plus a monospace face only when code is shown.

## Sources

- Google Fonts Knowledge: Pairing typefaces. https://fonts.google.com/knowledge/choosing_type/pairing_typefaces
- Google Fonts Knowledge: Pairing typefaces within a family & superfamily. https://fonts.google.com/knowledge/choosing_type/pairing_typefaces_within_a_family_superfamily
- Google Fonts Knowledge: Pairing typefaces using the font matrix (Indra Kupferschmid). https://fonts.google.com/knowledge/choosing_type/pairing_typefaces_based_on_their_construction_using_the_font_matrix
- Google Fonts Knowledge: Choosing typefaces that have optical sizes. https://fonts.google.com/knowledge/choosing_type/choosing_typefaces_that_have_optical_sizes
- Google Fonts Knowledge: A checklist for choosing type. https://fonts.google.com/knowledge/choosing_type/a_checklist_for_choosing_type
- Matthew Butterick, *Practical Typography*: Mixing fonts. https://practicaltypography.com/mixing-fonts.html ; Summary of key rules. https://practicaltypography.com/summary-of-key-rules.html
- Vox-ATypI classification. https://en.wikipedia.org/wiki/Vox-ATypI_classification ; Sans-serif subclasses. https://en.wikipedia.org/wiki/Sans-serif
- Material Design 3: Typography / applying type. https://m3.material.io/styles/typography/applying-type
- Typewolf pairing pages (Source Serif/Sans, Libre Franklin, Playfair Display, Alegreya Sans, Space Mono). https://www.typewolf.com/google-fonts
- Fontpair. https://fontpair.co/
- U.S. Web Design System font tokens. https://designsystem.digital.gov/design-tokens/typesetting/font-family/
- Google Fonts CSS2 API (used for verification). https://fonts.googleapis.com/css2
