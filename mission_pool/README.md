# Mission Pool

This directory contains mission cards for Warhammer 40K games.

## Structure

```
mission_pool/
├── mission_pool.json          # Configuration mapping letters to missions
├── deployment/                 # Deployment type images
│   ├── crucible_of_battle.png
│   ├── dawn_of_war.png
│   ├── hammer_and_anvil.png
│   ├── search_and_destroy.png
│   ├── sweeping_engagement.png
│   └── tipping_point.png
├── primary_mission/            # Primary mission images
│   ├── 1.png
│   ├── 9.png
│   ├── 10.png
│   ├── hidden_supplies.png
│   ├── linchpin.png
│   ├── purge_the_foe.png
│   ├── scorched_earth.png
│   ├── supply_drop.png
│   ├── take_and_hold.png
│   └── terraform.png
└── terrain_layout/             # Terrain layout images (randomly selected)
    ├── 1.png
    ├── 2.png
    ├── 3.png
    ├── 4.png
    ├── 5.png
    ├── 6.png
    ├── 7.png
    └── 8.png
```

## How it works

1. When a game starts, a random combination letter (A-J) is selected
2. Based on the letter, primary_mission and deployment are determined
3. One terrain_layout is randomly selected from the available options
4. All three images are sent to all game participants

## Configuration

Edit `mission_pool.json` to customize combinations:

```json
{
  "A": {
    "primary_mission": "take_and_hold",      // filename without .png
    "deployment": "sweeping_engagement",      // filename without .png
    "terrain_layout": [1, 2, 3, 4, 5, 6, 7, 8]  // numbers of available layouts
  }
}
```
