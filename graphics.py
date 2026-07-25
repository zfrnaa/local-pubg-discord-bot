from PIL import Image, ImageDraw, ImageFont
import io
import discord

def generate_stat_card(match_data):
    """
    Creates a dynamic visual stat card for the ENTIRE SQUAD with updated columns.
    """
    img = Image.new('RGB', (800, 500), color=(30, 33, 36))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("impact.ttf", 55)
        text_font = ImageFont.truetype("arial.ttf", 30) # Slightly smaller to fit new columns
        small_font = ImageFont.truetype("arial.ttf", 18)
    except IOError:
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # --- 1. Draw the Header ---
    draw.text((400, 30), "WINNER WINNER CHICKEN DINNER", fill=(241, 196, 15), font=title_font, anchor="mt")

    # Draw Column Headers (Adjusted X coordinates to fit 6 items)
    draw.text((40, 120), "PLAYER", fill=(170, 170, 170), font=small_font)
    draw.text((300, 120), "KILLS", fill=(170, 170, 170), font=small_font)
    draw.text((360, 120), "DAMAGE", fill=(170, 170, 170), font=small_font)
    draw.text((480, 120), "ASSISTS", fill=(170, 170, 170), font=small_font)
    draw.text((570, 120), "AWARD", fill=(170, 170, 170), font=small_font)

    draw.line([(30, 150), (770, 150)], fill=(170, 170, 170), width=2)

    # --- 2. Draw the Squad ---
    y_offset = 180

    for player in match_data['squad']:
        kills = player['kills']
        damage = player['damage']
        assists = player.get('assists', 0)
        longest_kill = player.get('longest_kill', 0)
        revives = player.get('revives', 0)

        # Dynamic Title Logic
        title = "Survivor"
        if kills == 0 and damage < 100:
            title = "Pacifist"
        if revives >= 2:
            title = "Medic"
        if longest_kill >= 150.0:
            title = "Sharpshooter"
        if damage >= 800.0:
            title = "Berserker"
        if kills >= 7:
            title = "Terminator"

        # Draw Row Data
        draw.text((40, y_offset), player['name'][:12], fill=(255, 255, 255), font=text_font) # Caps names at 12 chars to prevent overlap
        draw.text((300, y_offset), str(kills), fill=(255, 255, 255), font=text_font)
        draw.text((360, y_offset), str(damage), fill=(255, 255, 255), font=text_font)
        draw.text((480, y_offset), str(assists), fill=(255, 255, 255), font=text_font)
        draw.text((570, y_offset), title.upper(), fill=(231, 76, 60), font=text_font)

        y_offset += 60

    # --- 3. Package for Discord ---
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return discord.File(fp=buffer, filename="squad_win.png")

def generate_leaderboard_card(leaderboard_data):
    """
    Takes a sorted list of player stats and draws a leaderboard image.
    """
    # Create a taller canvas to fit multiple players
    img = Image.new('RGB', (800, 600), color=(30, 33, 36))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("impact.ttf", 55)
        text_font = ImageFont.truetype("arial.ttf", 35)
        small_font = ImageFont.truetype("arial.ttf", 25)
    except IOError:
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # Draw Title
    draw.text((400, 30), "CLAN LEADERBOARD", fill=(241, 196, 15), font=title_font, anchor="mt")

    # Draw Headers
    draw.text((100, 120), "RANK", fill=(170, 170, 170), font=small_font)
    draw.text((250, 120), "PLAYER", fill=(170, 170, 170), font=small_font)
    draw.text((550, 120), "K/D RATIO", fill=(170, 170, 170), font=small_font)
    draw.text((700, 120), "WINS", fill=(170, 170, 170), font=small_font, anchor="rt")

    # Draw a line under headers
    draw.line([(80, 160), (720, 160)], fill=(170, 170, 170), width=2)

    # Loop through the players and draw their stats row by row
    y_offset = 180
    for index, player in enumerate(leaderboard_data[:10]): # Limit to top 10 to fit on screen
        # Gold for 1st, Silver for 2nd, Bronze for 3rd, White for the rest
        if index == 0:
            color = (241, 196, 15)
        elif index == 1:
            color = (192, 192, 192)
        elif index == 2:
            color = (205, 127, 50)
        else:
            color = (255, 255, 255)

        draw.text((100, y_offset), f"#{index + 1}", fill=color, font=text_font)
        draw.text((250, y_offset), player['name'], fill=color, font=text_font)
        draw.text((550, y_offset), str(player['kd']), fill=color, font=text_font)
        draw.text((700, y_offset), str(player['wins']), fill=color, font=text_font, anchor="rt")

        y_offset += 50 # Move down for the next row

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return discord.File(fp=buffer, filename="clan_leaderboard.png")

# --- Local Testing Block ---
# If you run `python graphics.py` directly, it will test the layout using mock data
if __name__ == "__main__":
    print("Testing graphics generation...")

    mock_match_data = {
        "winPlace": 1,
        "squad": [
            {"name": "PlayerOne", "kills": 8, "damage": 1250.0, "assists": 2, "longest_kill": 210.5, "revives": 1},
            {"name": "PlayerTwo", "kills": 0, "damage": 50.0, "assists": 0, "longest_kill": 0, "revives": 3},
            {"name": "PlayerThree", "kills": 3, "damage": 450.0, "assists": 1, "longest_kill": 45.0, "revives": 0},
            {"name": "PlayerFour", "kills": 0, "damage": 10.0, "assists": 4, "longest_kill": 0, "revives": 0}
        ]
    }

    # Generate the image
    test_match_file = generate_stat_card(mock_match_data)

    # Save it to your folder
    from PIL import Image
    Image.open(test_match_file.fp).save("test_squad_win.png")
    print("Test complete! Open 'test_squad_win.png' in your folder to see the layout.")