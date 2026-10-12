# Yorkie emojis

17 custom emojis of a Yorkshire terrier: a golden topknot, upright ears (one flops on car rides),
a tongue that is usually out, and the blue harlequin and striped knit sweaters. They are drawn in
the VIXL Line style: 72×72 canvas, navy `#23364D` 1.7 px outlines, with details kept inside the 8 px margin.

![Yorkie emoji sheet](yorkie-emojis.png)

| Shortcode | | Shortcode | |
| --- | --- | --- | --- |
| `:yorkie:` | happy | `:yorkie_laugh:` | laughing |
| `:yorkie_blep:` | tongue out | `:yorkie_wow:` | surprised |
| `:yorkie_lick:` | nose lick | `:yorkie_grumpy:` | grumpy |
| `:yorkie_love:` | heart eyes | `:yorkie_cool:` | sunglasses |
| `:yorkie_puppy_eyes:` | pleading | `:yorkie_party:` | party hat |
| `:yorkie_sad:` | teary | `:yorkie_sweater:` | harlequin sweater |
| `:yorkie_sleepy:` | sleepy | `:yorkie_car_ride:` | car-seat carrier |
| `:yorkie_wink:` | wink | `:yorkie_wave:` | paw wave |
| `:yorkie_treat:` | bone | | |

## Files

- `packs/yorkie-discord.zip`, `packs/yorkie-slack.zip`: 128 px PNGs that pass each destination's checks,
  plus SVGs, VIXL masters, `index.html` preview and upload instructions.
- `packs/yorkie-images-512.zip`: 512 px transparent PNGs (stickers, messaging apps).
- `masters/*.vixl`: one editable master per emoji (separate vector shape layers); `svg/` holds the sources.
- `yorkie-emojis.vixl`: a document with all 17 registered as custom shortcodes. Type `:yorkie_blep:` in any of its text layers.

## Rebuild or edit

Change the shapes in `yorkie_art.py`, then run `python art/yorkie-emojis/build.py` from the repository root.
Or edit a master directly and register it again:

```bash
vixl -p art/yorkie-emojis/masters/yorkie.vixl render --out yorkie.png
vixl -p art/yorkie-emojis/yorkie-emojis.vixl emoji replace ':yorkie:' art/yorkie-emojis/masters/yorkie.vixl --name yorkie
vixl -p art/yorkie-emojis/yorkie-emojis.vixl emoji export --destination discord --out my-discord.zip
```
