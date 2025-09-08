import random

ROASTS_VALUE = [
    "{name} at ${sal:,.0f} for {pts:.1f} pts — coupon-clipper energy. Your spreadsheet has a cape.",
    "{name} returned {ppk:.2f} pts/$1K. That’s not value, that’s grand larceny.",
    "{name} paid for lunch and dessert. Opponents picking up the tip."
]

ROASTS_BUST = [
    "{name} at ${sal:,.0f} for {pts:.1f} pts — that’s boutique pricing for gas-station sushi.",
    "{name} delivered {ppk:.2f} pts/$1K. That’s a salary-cap sinkhole.",
    "{name} was a trust fall with no one behind you."
]

TEAM_TITLES = {
    "coupon_clipper": "🧾 Coupon Clipper of the Week",
    "dumpster_fire": "🔥 Dumpster Fire of the Week",
    "galaxy_brain": "🧠 Galaxy Brain (boldest correct pick)",
    "banana_peel": "🍌 Banana Peel (highest-confidence whiff)",
    "walk_of_shame": "🚶 Walk of Shame (Survivor bust)"
}

def roast_value(row):
    return random.choice(ROASTS_VALUE).format(name=row["Name"], sal=row["Salary"] or 0, pts=row["Pts"], ppk=row["Pts_per_$K"])

def roast_bust(row):
    return random.choice(ROASTS_BUST).format(name=row["Name"], sal=row["Salary"] or 0, pts=row["Pts"], ppk=row["Pts_per_$K"])

