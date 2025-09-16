# Master phrase bank (generic + sections) plus team-name pun banks.
# Keep it snarky but avoid slurs/personal attacks.

import re

def team_slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9\s_-]", "", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s

BANK = {
    # Dumpster Fire tiers
    "df_sub70": [
        "This wasn’t a lineup, it was a GoFundMe for your opponent.",
        "You didn’t set a lineup—you filed a missing players report.",
        "Scored like you drafted from an airplane safety card.",
        "If fantasy had relegation, you’d be in a beer league by lunch.",
        "That score needs witness protection.",
        "I’ve seen pop-up blockers put up more points.",
        "You benched points like it was a religion.",
        "Your lineup is what happens when autoplay picks.",
        "That wasn’t a game—that was a wellness check.",
        "The scoreboard tried to 404 your result out of mercy.",
        "Even the waiver wire said ‘keep it.’",
        "Your team is a bye week with a logo.",
        "Stat corrections won’t save this; a priest might.",
        "Trash day called—they won’t take biohazard.",
        "ESPN changed your projection to ‘thoughts and prayers.’",
        "The injury tent waved you in with no injuries—just vibes."
    ],
    "df_70s": [
        "You brought a spoon to a chainsaw party.",
        "That’s not a box score—that’s a Yelp review for sadness.",
        "Your flex had the energy of a Tuesday salad.",
        "Benching points like it’s tax season.",
        "Even your kicker asked for a trade.",
        "Your lineup was a commuter rail delay.",
        "Could’ve hit higher with nine fullbacks.",
        "Heimlich needed on that flex.",
        "Your team is allergic to end zones."
    ],
    "df_80s": [
        "Respectable tank job. Wink.",
        "You flirted with competence and ghosted it.",
        "You scored like the app was in low-power mode.",
        "Solid exhibition game. The regular season starts next week, maybe.",
        "It’s giving ‘middle manager of mediocrity.’",
        "Points showed up late and left early.",
        "You microwaved a steak and called it dinner.",
        "A participation trophy would decline this invite."
    ],

    # Fraud Watch
    "fraud": [
        "Record’s shiny; engine’s knocking. Paper tiger alert.",
        "Smoke, mirrors, and a coupon for disappointment.",
        "Trending like a meme: hot now, gone by Thursday.",
        "Schedule built your ego; reality wants a word.",
        "Your ceiling is actually the floor with good lighting.",
        "One primetime game away from exposure therapy.",
        "Built different—like a Jenga tower.",
        "House of cards, windy forecast.",
        "The vibes are undefeated; the math is not."
    ],

    # VP Crime Scene
    "vp_crime": [
        "Missed the velvet rope by a decimal—bouncer says try cardio.",
        "Decimal scoring remains an undefeated hater.",
        "This loss was brought to you by rounding.",
        "So close the app offered grief counseling.",
        "VPs were in the cart—Apple Pay failed.",
        "Next time bring a magnifying glass and two more points.",
        "You did everything but finish. Story of the season?",
        "Margin so thin it needs SPF."
    ],

    # Spotlight quotes (per team rotation)
    "quotes": [
        "I thought Derrick Henry was still 25.",
        "Projections are a suggestion.",
        "I set my lineup on airplane Wi-Fi.",
        "Correlation is just a rumor.",
        "Floor? I prefer trap doors.",
        "I chase steam like it owes me money.",
        "Stacked the wrong game with conviction.",
        "I build lineups with my heart and a dart.",
        "I thought bye weeks were optional.",
        "I faded common sense for leverage.",
        "My flex is my red flag.",
        "Variance is my love language.",
        "I saw one tweet and went all-in.",
        "Injuries are temporary, my tilt is permanent.",
        "I drafted vibes and prayed.",
        "Waivers are where I practice jazz.",
        "I use projections like horoscopes.",
        "My optimizer is a coin flip.",
        "Ceiling plays only—floor is lava.",
        "I’m saving points for playoffs.",
        "I let autoplay pick my flex.",
        "I trusted preseason highlights.",
        "Sleepers? I overslept.",
        "I zigged into a wood chipper.",
        "If chalk hurts, I double it.",
        "Usage? I prefer folklore.",
        "Yards after catch? I’m after vibes.",
        "I confuse momentum with meteorology."
    ],

    # Chalk bust tags
    "chalk_bust": [
        "Chalk melted on contact.",
        "Went full statue—zero separation.",
        "A cardio session in cleats.",
        "Got tackled by projection models.",
        "Hit the floor so hard it left a dent.",
        "Ghosted red zone like a bad date.",
        "More decoy than deploy.",
        "Air-mailed the entire slate.",
        "Screen pass to irrelevance."
    ],

    # Value praise
    "value_hit": [
        "Coupon clicked. Free points.",
        "Dollar menu masterpiece.",
        "Great value—chef’s kiss.",
        "Thrift store gem.",
        "PPP clinic.",
        "Waiver wire Michelin star.",
        "Clearance rack heater.",
        "Points-per-dollar poetry."
    ],

    # Survivor / Confidence color
    "survivor": [
        "Tightrope walked in flip-flops and stuck the landing.",
        "Brought training wheels to a drag race.",
        "Risked it for a Costco-sized biscuit.",
        "Consensus pick? Live a little.",
        "Your lifeline has butterfingers."
    ],
    "confidence": [
        "Stacked chalk like sandbags—slept fine.",
        "Bet dogs and found fleas (and a win).",
        "Your 16 was basically a TED Talk.",
        "Underdog parlay of emotions.",
        "Risk budget spent like stimulus checks."
    ],

    # Generic fallback heat
    "generic": [
        "That take aged like milk in August.",
        "You’re playing Minesweeper with your lineup.",
        "Waiver wire is typing…",
        "Your roster construction needs adult supervision.",
        "You tanked so gracefully the crowd applauded.",
        "Started from the bottom and tunneled.",
        "Touchdown equity filed Chapter 11.",
        "You’re the reason projections drink.",
        "Built different—like an Ikea chair missing three screws."
    ],
}

# Team-specific burns keyed by slug (use team_slug)
TEAM_BANK = {
  "freaks": [
    "Freaks? The only thing freaky was that efficiency.",
    "Freaks ran hot—thermostat set to ‘unsustainable.’",
    "Ringmaster vibes, clown-car execution.",
    "Freaks found points in couch cushions again.",
    "House of Freaks; foundation made of projections."
  ],
  "injury_inc": [
    "Injury Inc filed another workers’ comp claim at halftime.",
    "The only thing healthy at Injury Inc is the ego.",
    "Injury Inc—every lineup comes with a co-pay.",
    "Blue tent is your second home address.",
    "Projected points went on IR."
  ],
  "flatfootworks": [
    "FlatFootWorks—great footwork, tripped over the end zone.",
    "OSHA compliant, scoreboard non-compliant.",
    "Assembly line of almosts.",
    "You punched in; the points punched out.",
    "Industrial vibes, artisanal whiffs."
  ],
  "taint_toucher": [
    "PG-13 team name, G-rated points.",
    "NSFW username, safe-for-work box score.",
    "Spicy handle, mild salsa lineup.",
    "Edgy title, butter-knife production."
  ],
  "gbhdj14": [
    "GBHDJ14—looks like a password and got brute-forced.",
    "Two-factor auth, one-point offense.",
    "Strong password, weak finish.",
    "Version 14, points still in beta."
  ],
  "the_whack_pack": [
    "The Whack Pack—whacked your ceiling, packed up early.",
    "Packed potential, whack execution.",
    "Travel-size scoring—carry-on only.",
    "Comedy troupe with tragic timing."
  ],
  "swamp_rabbits": [
    "Swamp Rabbits hopped; then sank in the mud.",
    "Bayou vibes, bogged-down box score.",
    "Fast start, gator finish.",
    "Hopped lanes, stuck in the muck."
  ],
  "dominators": [
    "Dominators—great branding, aspirational results.",
    "You dominated the pregame talk.",
    "Paper Dominators—rain forecast.",
    "Alpha energy, beta production."
  ],
  "femmes": [
    "FEMMES—finesse for days, finish needs directions.",
    "Catwalk cadence, goal-line traffic.",
    "Elegance is eternal; so was that 3-and-out.",
    "Haute couture, off-the-rack points."
  ],
  "circle_the_wagons": [
    "Circle the Wagons—unfortunately circled the drain.",
    "Wagons circled; offense went square.",
    "Trail boss energy, ox-cart speed.",
    "Manifest destiny, manifest punting."
  ],
  "the_mayor": [
    "The Mayor kissed babies, not the end zone.",
    "Campaign strong; concession speech stronger.",
    "Polling well, scoring poorly.",
    "Filibustered the red zone."
  ],
  "bang": [
    "BANG—more like tap. You knocked politely.",
    "BANG! (confetti cannon jammed).",
    "Sound effect > effect.",
    "Volume up, value down."
  ],
  "polish_pounders": [
    "Pounders got pounded by variance.",
    "Hammer brand, rubber-mallet results.",
    "Heavy hands, feather points.",
    "You brought a mallet to a math test."
  ],
  "bubba_fell_in_the_creek": [
    "Name checks out—Bubba belly-flopped again.",
    "Threw a rope; it was a noodle.",
    "Upstream dreams, downstream points.",
    "Creek rise, hopes sink."
  ],
  "fast_and_ferocious": [
    "Fast and Ferocious—fast to tilt, ferocious to misclick.",
    "Quarter-mile speed, lawn-mower torque.",
    "Fast start, ferocious stall.",
    "Pit crew forgot the tires again."
  ],
  "politically_incorrect": [
    "Politically Incorrect—bi-partisan collapse.",
    "Across the aisle to shake hands with defeat.",
    "Executive orders to punt.",
    "Debated starts, lost on points."
  ],
  "mikes_misery": [
    "Mike’s Misery—truth in advertising.",
    "Mike’s Misery: now with extra Misery.",
    "If pain scored, you’d be undefeated.",
    "The Misery Index called; you’re a blue chip."
  ],
}

def expand_team_bank(team_bank: dict) -> dict:
    return {f"name:{slug}": lines[:] for slug, lines in team_bank.items()}

# Merge team-specific categories into BANK
BANK.update(expand_team_bank(TEAM_BANK))
