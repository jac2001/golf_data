# How to Get Tournament Fields for Predictions

## Option 1: Manual Entry (Quickest for Now)

Since The American Express hasn't started yet, the easiest way is to manually create the field CSV.

### Steps:

1. **Go to the PGA Tour website**:
   - https://www.pgatour.com/tournaments/2026/the-american-express/R2026002/field

2. **Copy the player list** (you can select all names on the page)

3. **Create CSV file** at `data/fields/american_express_2026.csv`:

```csv
player_id,player_name
46046,Scottie Scheffler
33448,Rory McIlroy
47959,Jon Rahm
50525,Viktor Hovland
48081,Collin Morikawa
...
```

### Quick Helper Script:

I'll create a helper that lets you paste names and automatically matches them to player IDs from your database.

---

## Option 2: Use Existing Field from Historical Data

For testing purposes, you can use a historical field from 2025:

```python
import pandas as pd

# Load 2025 American Express field
master_df = pd.read_csv('data/processed/master_training_data_2020_2025.csv')

# Get 2025 American Express field (tournament_id for American Express)
amex_2025 = master_df[
    (master_df['year'] == 2025) &
    (master_df['tournament_name'].str.contains('AMERICAN EXPRESS', case=False, na=False))
]

# Get unique players
field = amex_2025[['player_id', 'player_name']].drop_duplicates()

# Save
field.to_csv('data/fields/american_express_test.csv', index=False)
print(f"Created test field with {len(field)} players")
```

---

## Option 3: Scraper Script (For When API Works)

The scraper I created will work once the tournament starts or if the API becomes accessible.

---

## Let's Do Option 2 (Quick Test)

I'll create a test field from 2025 data so you can test your predictions right now!