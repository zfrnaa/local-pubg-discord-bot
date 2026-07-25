import sqlite3
import asyncio
import discord
from discord.ext import commands
from discord.ext import tasks
from discord import app_commands
import sqlite3
import pubg_api
import graphics
import os
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()

class PUBGTrackerBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=discord.Intents.default())

    async def setup_hook(self):
        await self.tree.sync()
        setup_database() # Start the database to boots up
        auto_track_matches.start() #background loop checking
        print("Bot is ready and database is connected.")

bot = PUBGTrackerBot()

# Run this once when the bot starts
def setup_database():
    conn = sqlite3.connect('pubg_clan.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clan_members (
            pubg_name TEXT PRIMARY KEY,
            discord_id TEXT,
            account_id TEXT,
            last_match_id TEXT
        )
    ''')
    conn.commit()
    conn.close()


@bot.tree.command(name="track_me", description="Join the clan leaderboard.")
async def track_me(interaction: discord.Interaction, pubg_name: str):
    await interaction.response.defer(ephemeral=True)

    account_id = pubg_api.get_account_id(pubg_name)

    conn = sqlite3.connect('pubg_clan.db')
    cursor = conn.cursor()
    # Notice we added last_match_id and pass None as the default
    cursor.execute('''
        INSERT OR REPLACE INTO clan_members (pubg_name, discord_id, account_id, last_match_id)
        VALUES (?, ?, ?, ?)
    ''', (pubg_name, str(interaction.user.id), account_id, None))
    conn.commit()
    conn.close()

    await interaction.followup.send(f"✅ Successfully linked <@{interaction.user.id}> to PUBG player **{pubg_name}**!")

@bot.tree.command(name="match_report", description="Get your latest match stats.")
async def match_report(interaction: discord.Interaction, player_name: str):
    await interaction.response.defer()

    # 1. Fetch match stats and telemetry
    match_data = pubg_api.fetch_and_parse_match(player_name)

    # 2. ALWAYS build the 4-column text embed for the whole squad
    embed_color = discord.Color.gold() if match_data['winPlace'] == 1 else discord.Color.red()
    embed = discord.Embed(
        title=f"Match Report - Placement: #{match_data['winPlace']}",
        color=embed_color
    )

    for player in match_data['squad']:
        stats_text = (
            f"**Kills:** {player['kills']}\n"
            f"**Damage:** {player['damage']}\n"
            f"**Knocked By:** {player['knocked_by']}\n"
            f"**Killed By:** {player['killed_by']}"
        )
        embed.add_field(name=player['name'], value=stats_text, inline=True)

    # 3. Check for Chicken Dinner
    if match_data['winPlace'] == 1:
        # WINNER! Generate the Stat Card Graphic
        stat_card_file = graphics.generate_stat_card(match_data)

        # Send BOTH the image and the 4-column embed
        await interaction.followup.send(
            content=f"🏆 **WINNER WINNER CHICKEN DINNER!** 🏆\nAmazing match, **{player_name}**!",
            embed=embed,
            file=stat_card_file
        )

    else:
        # DID NOT WIN. Send ONLY the 4-column embed we built in Step 2
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="clan_leaderboard", description="View the server's PUBG rankings.")
async def clan_leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()

    # 1. Get all tracked members from SQLite
    conn = sqlite3.connect('pubg_clan.db')
    cursor = conn.cursor()
    cursor.execute("SELECT pubg_name, account_id FROM clan_members")
    members = cursor.fetchall()

    # 2. Fetch lifetime/season stats for each member
    leaderboard_data = []
    for pubg_name, account_id in members:
        # Make a call to: /players/{account_id}/seasons/lifetime
        stats = pubg_api.get_lifetime_stats(account_id)

        # Calculate K/D Ratio
        kills = stats['kills']
        deaths = stats['roundsPlayed'] - stats['wins']
        kd_ratio = kills / deaths if deaths > 0 else kills

        leaderboard_data.append({
            "name": pubg_name,
            "kd": round(kd_ratio, 2),
            "wins": stats['wins']
        })

    # 3. Sort by highest K/D Ratio
    leaderboard_data.sort(key=lambda x: x['kd'], reverse=True)

    # Generate the image instead of text!
    leaderboard_file = graphics.generate_leaderboard_card(leaderboard_data)

    await interaction.followup.send(
        content="📊 **Current Server Clan Rankings**",
        file=leaderboard_file
    )

@tasks.loop(minutes=5)
async def auto_track_matches():
    """Background loop that checks for new matches every 5 minutes."""
    feed_channel_id = os.getenv('FEED_CHANNEL_ID')
    if not feed_channel_id:
        return # Failsafe if you forgot to add the ID to the .env file

    channel = bot.get_channel(int(feed_channel_id))
    if not channel:
        return

    # 1. Pull all tracked players from the database
    conn = sqlite3.connect('pubg_clan.db')
    cursor = conn.cursor()
    cursor.execute("SELECT pubg_name, account_id, last_match_id FROM clan_members")
    members = cursor.fetchall()

    for pubg_name, account_id, saved_match_id in members:
        # 2. Lightweight check for their current latest match
        latest_id = pubg_api.check_latest_match_id(account_id)

        # 3. If a match exists and it doesn't match our saved memory, it's new!
        if latest_id and latest_id != saved_match_id:
            try:
                # Process the full match data just like the slash command does
                match_data = pubg_api.fetch_and_parse_match(pubg_name)

                embed_color = discord.Color.gold() if match_data['winPlace'] == 1 else discord.Color.red()
                embed = discord.Embed(
                    title=f"Auto Tracker: Match Report - Placement: #{match_data['winPlace']}",
                    color=embed_color
                )

                for player in match_data['squad']:
                    # Calculate minutes and seconds
                    minutes = int(player['time_survived'] // 60)
                    seconds = int(player['time_survived'] % 60)

                    stats_text = (
                        f"**Kills:** {player['kills']}\n"
                        f"**Knocks:** {player['knocks']}\n"
                        f"**Damage:** {player['damage']}\n"
                        f"**Assists:** {player['assists']}\n"
                        f"**Revives:** {player['revives']}\n"
                        f"**Longest kill:** {player['longest_kill']}m\n"
                        f"**Vehicle distance:** {player['ride_distance']}km\n"
                        f"**Distance walked:** {player['walk_distance']}km\n"
                        f"**Time survived:** {minutes}m {seconds}s"
                    )
                    embed.add_field(name=player['name'], value=stats_text, inline=True)

                if match_data['winPlace'] == 1:
                    stat_card_file = graphics.generate_stat_card(match_data)
                    await channel.send(
                        content=f"🏆 **WINNER WINNER CHICKEN DINNER!** 🏆\n**{pubg_name}** just won a match!",
                        embed=embed,
                        file=stat_card_file
                    )
                else:
                    await channel.send(content=f"**{pubg_name}** just finished a match:", embed=embed)

                # 4. Update the database memory so we don't post it again next loop
                cursor.execute("UPDATE clan_members SET last_match_id = ? WHERE pubg_name = ?", (latest_id, pubg_name))
                conn.commit()

            except Exception as e:
                print(f"Error parsing auto-match for {pubg_name}: {e}")

        # Rate Limiter: Pause for 2 seconds before checking the next player
        await asyncio.sleep(2)

    conn.close()

# Run the bot with token
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

bot.run(DISCORD_TOKEN)