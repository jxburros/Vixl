"""Card data: twelve Aetherling Spirits (with deliberately tricky rows) and the element/rarity tables."""

ELEMENT_COLORS = {
    # element: (main, dark, light)
    "Ember": ("#ff6b35", "#2a0905", "#ffd166"),
    "Tide": ("#2ec4ff", "#03182b", "#c9f6ff"),
    "Grove": ("#6fd08c", "#071f10", "#e6ffd9"),
    "Storm": ("#b388ff", "#130a2e", "#f1e6ff"),
    "Void": ("#ff4fa3", "#1a0412", "#ffd6ec"),
}

RARITY = {
    # rarity: (badge color, pip string)
    "Common": ("#c9d1d9", "◆"),
    "Rare": ("#4cc9f0", "◆◆"),
    "Epic": ("#c77dff", "◆◆◆"),
    "Legendary": ("#ffc94a", "◆◆◆◆"),
}

# Each card: name, element, rarity, kind, cost, atk, def, spd, ability_name, ability, flavor, seed
CARDS = [
    ("Cinderwisp", "Ember", "Common", "Spirit — Wisp", 1, 2, 1, 4,
     "Kindle", "When Cinderwisp enters play, give another Ember spirit +1 ATK until end of turn.",
     "“Follow the small light,” the old guides said. Few asked where it led.", 3),
    ("Tidecaller Maru", "Tide", "Rare", "Spirit — Herald", 3, 2, 4, 3,
     "Undertow", "Return target spirit with SPD 2 or less to its owner’s hand.",
     "The harbor bells ring twice before she rises.", 8),
    ("Mossback Elder", "Grove", "Common", "Spirit — Ancient", 4, 3, 6, 1,
     "Deep Roots", "Mossback Elder can’t be moved by effects your opponents control.",
     "It has been asleep since the forest was a single seed.", 5),
    ("Galvanir", "Storm", "Epic", "Spirit — Thunderwing", 5, 6, 3, 6,
     "Chain Spark", "Deal 2 damage to each enemy spirit. If one is destroyed this way, repeat once.",
     "Count the seconds between the flash and the roar. Then stop counting.", 11),
    ("Nyxshade", "Void", "Rare", "Spirit — Lurker", 3, 4, 2, 5,
     "Eclipse", "Nyxshade can’t be targeted while you control another Void spirit.",
     "Where the lantern fails, she is already waiting.", 5),
    # tricky: very long name
    ("Archsovereign Pyrrhaxion, the Unquenchable Ember of the Ninth Caldera", "Ember", "Legendary",
     "Spirit — Primordial", 9, 9, 8, 4,
     "Unending Pyre", "At the start of each turn, deal 1 damage to every other spirit. Pyrrhaxion heals 1 for each spirit damaged.",
     "Nine calderas. Nine kings. One fire that never learned to die.", 21),
    # tricky: unicode (accents, ligature, macron)
    ("Ætherwyrm Ölsén", "Storm", "Rare", "Spirit — Wyrm", 4, 5, 3, 4,
     "Fjörd Gale", "Push each enemy spirit with DEF 3 or less to the back row.",
     "“Skål to the wind,” øne sailor laughed — and the wind answered.", 17),
    # tricky: very long flavor text
    ("Lantern Moth", "Grove", "Common", "Spirit — Swarm", 2, 1, 2, 5,
     "Glimmer", "When Lantern Moth is destroyed, draw a card.",
     "They gather at dusk in the hollows of the old wood, a thousand small lamps that drift and dim and "
     "brighten again, and the villagers say each one is a promise somebody forgot to keep, still circling the "
     "place where it was made, still waiting to be remembered, still burning, patiently, against the coming dark "
     "of a winter that has not yet arrived.", 33),
    # tricky: CJK + emoji outside the display font's coverage
    ("光の狐 Hikari-no-Kitsune ✨", "Tide", "Epic", "Spirit — Kitsune", 6, 5, 4, 7,
     "Ninefold Mirage", "Create two 1/1 Mirage tokens. They copy Hikari’s ability text.",
     "「光を追う者は、影に迷う」 — old proverb", 42),
    # tricky: very long ability text
    ("Grimward Sentinel", "Void", "Epic", "Spirit — Warden", 6, 3, 9, 1,
     "Oath of the Threshold",
     "Enemy spirits can’t attack you unless their controller pays 2 for each. Whenever an enemy spirit "
     "attacks another player, Grimward Sentinel gets +1 DEF permanently and you may return a destroyed Void "
     "spirit from your discard pile to your hand. This ability can’t be copied, negated or moved.",
     "It has never once opened the gate.", 50),
    # tricky: unfilled placeholder copy that slipped into the data
    ("[CARD NAME]", "Storm", "Common", "Spirit — TBD", 0, 0, 0, 0,
     "TBD", "Lorem ipsum dolor sit amet.", "TODO: flavor text", 61),
    ("Seraphel, Dawn’s Last Light", "Ember", "Legendary", "Spirit — Seraph", 8, 7, 7, 6,
     "Daybreak", "When Seraphel enters play, restore every friendly spirit to full DEF and give them +2 SPD.",
     "The sky remembers her color long after she has gone.", 77),
    ("Riftling", "Void", "Common", "Spirit — Imp", 1, 1, 1, 6,
     "Blink", "Riftling can swap places with an adjacent friendly spirit once per turn.",
     "Here. There. Behind you.", 88),
]

FIELDS = ["name", "element", "rarity", "kind", "cost", "atk", "def", "spd", "ability_name", "ability", "flavor",
          "seed"]
