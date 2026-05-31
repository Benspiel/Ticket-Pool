import discord
from discord.ext import commands
from discord import app_commands
import json


def load_config() -> dict:
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


class TicketDropdown(discord.ui.Select):
    def __init__(self, options_config: list[dict]):
        options = [
            discord.SelectOption(
                label=opt["label"],
                description=opt.get("description", ""),
                emoji=opt.get("emoji"),
            )
            for opt in options_config
        ]
        super().__init__(
            placeholder="Select a ticket category...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = load_config()
        guild = interaction.guild
        user = interaction.user
        category_id = config.get("ticket_category_id")
        support_role_ids = config.get("support_role_ids", [])
        selected = self.values[0]

        category = guild.get_channel(category_id) if category_id else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
        }

        for role_id in support_role_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True,
                )

        channel_name = f"ticket-{selected.lower()}-{user.name}".replace(" ", "-")

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket created by {user} – {selected}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to create channels.", ephemeral=True
            )
            return

        await ticket_channel.send(
            f"{user.mention} has created a new ticket.\n**Category:** {selected}"
        )

        await interaction.followup.send(
            f"Your ticket has been created: {ticket_channel.mention}", ephemeral=True
        )


class TicketView(discord.ui.View):
    def __init__(self, options_config: list[dict]):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown(options_config))


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup-tickets", description="Send the ticket panel to the configured channel")
    @app_commands.default_permissions(administrator=True)
    async def setup_tickets(self, interaction: discord.Interaction):
        config = load_config()
        channel_id = config.get("ticket_channel_id")
        channel = interaction.guild.get_channel(channel_id)

        if channel is None:
            await interaction.response.send_message(
                "Ticket channel not found. Check `ticket_channel_id` in config.json.",
                ephemeral=True,
            )
            return

        view = TicketView(config["ticket_options"])
        embed = discord.Embed(
            title="Support Tickets",
            description="Select a category below to open a new ticket.",
            color=discord.Color.blurple(),
        )
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"Ticket panel sent to {channel.mention}.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
