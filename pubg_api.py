import requests
import os
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()

# --- Configuration ---
PUBG_API_KEY = os.getenv("PUBG_API_KEY")
PLATFORM = "steam" # Change to 'psn', 'xbox', or 'kakao' if needed

HEADERS = {
    "Authorization": f"Bearer {PUBG_API_KEY}",
    "Accept": "application/vnd.api+json"
}

BASE_URL = f"https://api.pubg.com/shards/{PLATFORM}"

def check_latest_match_id(account_id: str) -> str:
    """Lightweight check to get the latest match ID without downloading heavy telemetry."""
    url = f"{BASE_URL}/players?filter[playerIds]={account_id}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        try:
            return response.json()['data'][0]['relationships']['matches']['data'][0]['id']
        except (IndexError, KeyError):
            return None
    return None

def get_account_id(player_name: str) -> str:
    """Fetches the unique account ID for a given player name."""
    url = f"{BASE_URL}/players?filter[playerNames]={player_name}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        data = response.json()
        return data['data'][0]['id']
    else:
        raise Exception(f"Player {player_name} not found. Check the name and try again.")

def get_lifetime_stats(account_id: str) -> dict:
    """Fetches lifetime stats for the clan leaderboard."""
    url = f"{BASE_URL}/players/{account_id}/seasons/lifetime"
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        data = response.json()
        # Extracting squad FPP stats as the default leaderboard metric
        # You can change this to 'squad' for TPP, or aggregate them
        stats = data['data']['attributes']['gameModeStats']['squad-fpp']
        return {
            "kills": stats.get('kills', 0),
            "wins": stats.get('wins', 0),
            "roundsPlayed": stats.get('roundsPlayed', 0)
        }
    return {"kills": 0, "wins": 0, "roundsPlayed": 0}

def fetch_and_parse_match(player_name: str) -> dict:
    """Fetches the latest match, finds the full squad, and parses combat data."""
    # 1. Get the player's account ID and their latest match ID
    url = f"{BASE_URL}/players?filter[playerNames]={player_name}"
    player_resp = requests.get(url, headers=HEADERS).json()

    try:
        latest_match_id = player_resp['data'][0]['relationships']['matches']['data'][0]['id']
    except IndexError:
        raise Exception("No recent matches found for this player.")

    # 2. Get the match details and telemetry URL
    match_url = f"{BASE_URL}/matches/{latest_match_id}"
    match_resp = requests.get(match_url, headers={"Accept": "application/vnd.api+json"}).json()

    telemetry_url = None
    for item in match_resp.get("included", []):
        if item.get("type") == "asset":
            telemetry_url = item["attributes"]["URL"]
            break

    if not telemetry_url:
        raise Exception("Telemetry data is not yet available for this match.")

    # --- NEW SQUAD TRACING LOGIC ---

    # 3. Create a map of ALL players in the server for easy lookup
    participants_map = {}
    for item in match_resp.get("included", []):
        if item.get("type") == "participant":
            participants_map[item["id"]] = item["attributes"]["stats"]

    # 4. Find our requested player's ID
    target_id = None
    for pid, stats in participants_map.items():
        if stats["name"] == player_name:
            target_id = pid
            break

    if not target_id:
        raise Exception("Player was not found in the match data.")

    # 5. Find the Roster (Squad) that contains our player
    squad_stats = {}
    win_place = participants_map[target_id]["winPlace"]

    for item in match_resp.get("included", []):
        if item.get("type") == "roster":
            p_data = item["relationships"]["participants"]["data"]
            p_ids = [p["id"] for p in p_data]

            # If our player is in this squad, grab everyone!
            if target_id in p_ids:
                for pid in p_ids:
                    p_stats = participants_map[pid]

                    death_type = p_stats.get("deathType", "alive")
                    if death_type == "alive":
                        default_killed_by = "Survived"
                    elif death_type == "logout":
                        default_killed_by = "Disconnected (Left Match)"
                    elif death_type == "suicide":
                        default_killed_by = "Suicide"
                    elif death_type == "byzone":
                        default_killed_by = "Blue Zone"
                    else:
                        default_killed_by = "Unknown"

                    squad_stats[p_stats["name"]] = {
                        "name": p_stats["name"],
                        "kills": p_stats.get("kills", 0),
                        "damage": round(p_stats.get("damageDealt", 0.0), 2),
                        "assists": p_stats.get("assists", 0),
                        "revives": p_stats.get("revives", 0),
                        "longest_kill": round(p_stats.get("longestKill", 0.0), 2),
                        "ride_distance": round(p_stats.get("rideDistance", 0.0) / 1000, 2),
                        "walk_distance": round(p_stats.get("walkDistance", 0.0) / 1000, 2),
                        "time_survived": p_stats.get("timeSurvived", 0),
                        "knocked_by": [],
                        "killed_by": default_killed_by
                    }
                break

    # 6. Parse Telemetry JUST for Knocks and Kills for the squad
    telemetry_data = requests.get(telemetry_url).json()

    for event in telemetry_data:
        event_type = event.get("_T")

        # --- TRACKING KILLS ---
        if event_type == "LogPlayerKill":
            victim = event.get("victim")
            killer = event.get("killer")

            # Only track if the victim is in our squad
            if victim and victim.get("name") in squad_stats:
                victim_name = victim["name"]

                # Default fallback
                killer_name = "Environment"

                # Check if killer exists AND has a valid name
                if killer and killer.get("name"):
                    killer_name = killer["name"]
                else:
                    # If no killer name, check HOW they died
                    reason = event.get("damageReason", "Unknown")
                    if reason == "Groggy":
                        killer_name = "Bled Out"
                    elif reason == "BlueZone":
                        killer_name = "Blue Zone"
                    elif reason != "Unknown":
                        killer_name = reason # e.g., "Falling" or "RedZone"

                squad_stats[victim_name]["killed_by"] = killer_name

        # --- TRACKING KNOCKS ---
        elif event_type == "LogPlayerMakeGroggy":
            victim = event.get("victim")
            attacker = event.get("attacker")

            if victim and victim.get("name") in squad_stats:
                victim_name = victim["name"]

                attacker_name = "Environment"
                if attacker and attacker.get("name"):
                    attacker_name = attacker["name"]
                else:
                    reason = event.get("damageReason", "Unknown")
                    if reason == "BlueZone":
                        attacker_name = "Blue Zone"
                    elif reason != "Unknown":
                        attacker_name = reason

                squad_stats[victim_name]["knocked_by"].append(attacker_name)

    # 7. Format the lists into a final array
    final_squad_list = []
    for name, data in squad_stats.items():
        data["knocked_by"] = ", ".join(data["knocked_by"]) if data["knocked_by"] else "None"
        final_squad_list.append(data)

    # Sort the list so the player who requested the stats is always at the top!
    final_squad_list.sort(key=lambda x: x["name"] != player_name)

    return {
        "winPlace": win_place,
        "squad": final_squad_list
    }