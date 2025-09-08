import random

ROASTS_VALUE = [
    "{name} at ${sal:,.0f} for {pts:.1f} pts — coupon-clipper energy.",
    "{name} returned {ppk:.2f} pts/$1K. That’s grand larceny.",
    "{name} paid for lunch and dessert. Opponents picked up the tip."
]

ROASTS_BUST = [
    "{name} at ${sal:,.0f} for {pts:.1f} pts — boutique pricing for gas-station sushi.",
    "{name} delivered {ppk:.2f} pts/$1K — salary-cap sinkhole.",
    "{name} was a trust fall with no one behind you."
]

def roast_value(row):
    return random.choice(ROASTS_VALUE).format(name=row["Name"], sal=row["Salary"] or 0, pts=row["Pts"], ppk=row["Pts_per_$K"])

def roast_bust(row):
    return random.choice(ROASTS_BUST).format(name=row["Name"], sal=row["Salary"] or 0, pts=row["Pts"], ppk=row["Pts_per_$K"])
