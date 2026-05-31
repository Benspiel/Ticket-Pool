import json
from pathlib import Path
from random import randint

import discord
from discord.ext import commands


BANNER_PATH = Path("ticket_banner.png")
TICKET_SELECT_ID = "ticket_pool:create"
TICKET_CLOSE_ID = "ticket_pool:close"


def load_config() -> dict:
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def create_banner_file() -> discord.File | None:
    if not BANNER_PATH.exists():
        return None
    return discord.File(BANNER_PATH, filename="ticket_banner.png")


def create_ticket_topic(user: discord.abc.User, category: str, ticket_id: int) -> str:
    return f"ticket_owner_id={user.id};ticket_category={category};ticket_id={ticket_id}"


def parse_ticket_topic(topic: str | None) -> dict[str, str]:
    if not topic:
        return {}

    values = {}
    for part in topic.split(";"):
        key, separator, value = part.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def shorten_text(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def find_option_config(config: dict, label: str) -> dict:
    for option in config.get("ticket_options", []):
        if option.get("label") == label:
            return option
    return {}


def get_question_for_category(config: dict, category: str) -> str:
    option = find_option_config(config, category)
    return str(option.get("question", "")).strip()


def create_ticket_embed(
    user: discord.abc.User, category: str, ticket_id: int, reason: str | None = None
) -> discord.Embed:
    reason_text = reason.strip() if reason else "Nicht angegeben"
    embed = discord.Embed(
        description=(
            f"Hallo {user.mention}! Ein Teammitglied hilft dir gleich weiter.\n"
            "Bitte beschreibe dein Anliegen in der Zwischenzeit so genau wie möglich."
        ),
        color=discord.Color.green(),
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(name="Ticket ID", value=str(ticket_id), inline=True)
    embed.add_field(name="Kategorie", value=category, inline=True)
    embed.add_field(name="Ersteller", value=user.mention, inline=True)
    embed.add_field(name="Grund", value=shorten_text(reason_text, 1024), inline=False)

    if BANNER_PATH.exists():
        embed.set_image(url="attachment://ticket_banner.png")

    return embed


def create_panel_embed() -> discord.Embed:
    return discord.Embed(
        title="Support Tickets",
        description="Wähle unten eine Kategorie aus, um ein neues Ticket zu öffnen.",
        color=discord.Color.blurple(),
    )


def user_can_close_ticket(interaction: discord.Interaction) -> bool:
    config = load_config()
    support_role_ids = set(config.get("support_role_ids", []))
    member = interaction.user

    if not isinstance(member, discord.Member):
        return False

    return any(role.id in support_role_ids for role in member.roles)


def find_existing_ticket(
    guild: discord.Guild, user: discord.abc.User, category: str
) -> discord.TextChannel | None:
    for channel in guild.text_channels:
        ticket_data = parse_ticket_topic(channel.topic)
        if (
            ticket_data.get("ticket_owner_id") == str(user.id)
            and ticket_data.get("ticket_category") == category
        ):
            return channel
    return None


async def create_ticket(
    interaction: discord.Interaction, selected: str, reason: str | None = None
):
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    config = load_config()
    guild = interaction.guild
    user = interaction.user
    category_id = config.get("ticket_category_id")
    support_role_ids = config.get("support_role_ids", [])

    if guild is None:
        await interaction.followup.send(
            "Tickets können nur auf einem Server erstellt werden.", ephemeral=True
        )
        return

    existing_ticket = find_existing_ticket(guild, user, selected)
    if existing_ticket:
        await interaction.followup.send(
            f"Du hast bereits ein offenes Ticket: {existing_ticket.mention}",
            ephemeral=True,
        )
        return

    category = guild.get_channel(category_id) if category_id else None
    ticket_id = randint(1000, 9999)

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
            topic=create_ticket_topic(user, selected, ticket_id),
            overwrites=overwrites,
            reason=f"Ticket erstellt von {user} - {selected}",
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "Ich habe keine Berechtigung, Ticket-Channels zu erstellen.",
            ephemeral=True,
        )
        return

    await ticket_channel.send(f"{user.mention} hat ein neues Ticket erstellt.")

    embed = create_ticket_embed(user, selected, ticket_id, reason)
    file = create_banner_file()
    if file:
        await ticket_channel.send(embed=embed, file=file, view=TicketCloseView())
    else:
        await ticket_channel.send(embed=embed, view=TicketCloseView())

    await interaction.followup.send(
        f"Dein Ticket wurde erstellt: {ticket_channel.mention}", ephemeral=True
    )


class TicketQuestionModal(discord.ui.Modal):
    def __init__(self, category: str, question: str):
        super().__init__(title=shorten_text(f"Ticket: {category}", 45))
        self.category = category
        self.answer = discord.ui.TextInput(
            label=shorten_text(question, 45),
            placeholder=shorten_text(question, 100),
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
        )
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, self.category, str(self.answer.value))


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
            custom_id=TICKET_SELECT_ID,
            placeholder="Kategorie auswählen...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        config = load_config()
        guild = interaction.guild
        selected = self.values[0]

        if guild is None:
            await interaction.response.send_message(
                "Tickets können nur auf einem Server erstellt werden.", ephemeral=True
            )
            return

        existing_ticket = find_existing_ticket(guild, interaction.user, selected)
        if existing_ticket:
            await interaction.response.send_message(
                f"Du hast bereits ein offenes Ticket: {existing_ticket.mention}",
                ephemeral=True,
            )
            return

        question = get_question_for_category(config, selected)
        if question:
            await interaction.response.send_modal(TicketQuestionModal(selected, question))
            return

        await create_ticket(interaction, selected)


class TicketView(discord.ui.View):
    def __init__(self, options_config: list[dict]):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown(options_config))


class TicketCloseConfirmView(discord.ui.View):
    def __init__(self, requester_id: int):
        super().__init__(timeout=60)
        self.requester_id = requester_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True

        await interaction.response.send_message(
            "Nur die Person, die das Schließen gestartet hat, kann hier bestätigen.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Bestätigen", style=discord.ButtonStyle.danger)
    async def confirm_close(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.edit_message(
                content="Dieses Ticket kann hier nicht geschlossen werden.",
                view=None,
            )
            return

        if not user_can_close_ticket(interaction):
            await interaction.response.edit_message(
                content="Du darfst dieses Ticket nicht schließen.",
                view=None,
            )
            return

        channel = interaction.channel
        await interaction.response.edit_message(
            content="Ticket wird geschlossen...",
            view=None,
        )
        await channel.delete(reason=f"Ticket geschlossen von {interaction.user}")

    @discord.ui.button(label="Abbrechen", style=discord.ButtonStyle.secondary)
    async def cancel_close(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content="Schließen abgebrochen.",
            view=None,
        )


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Schließen",
        style=discord.ButtonStyle.danger,
        custom_id=TICKET_CLOSE_ID,
    )
    async def close_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "Dieses Ticket kann hier nicht geschlossen werden.", ephemeral=True
            )
            return

        if not user_can_close_ticket(interaction):
            await interaction.response.send_message(
                "Du darfst dieses Ticket nicht schließen.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Möchtest du dieses Ticket wirklich schließen?",
            view=TicketCloseConfirmView(interaction.user.id),
            ephemeral=True,
        )


async def send_ticket_panel(channel: discord.TextChannel, options_config: list[dict]):
    await channel.send(embed=create_panel_embed(), view=TicketView(options_config))


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.panel_sent = False
        config = load_config()
        self.bot.add_view(TicketView(config["ticket_options"]))
        self.bot.add_view(TicketCloseView())

    @commands.Cog.listener()
    async def on_ready(self):
        if self.panel_sent:
            return

        config = load_config()
        channel_id = config.get("ticket_channel_id")
        channel = self.bot.get_channel(channel_id) if channel_id else None

        if channel is None and channel_id:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.DiscordException as e:
                print(f"Ticket-Channel nicht gefunden: {e}")
                return

        if not isinstance(channel, discord.TextChannel):
            print("Ticket-Channel nicht gefunden. Prüfe `ticket_channel_id` in config.json.")
            return

        try:
            await channel.purge(limit=None, reason="Ticket-Panel beim Start zurückgesetzt")
            await send_ticket_panel(channel, config["ticket_options"])
            self.panel_sent = True
            print(f"Ticket-Panel in #{channel.name} zurückgesetzt.")
        except discord.Forbidden:
            print("Mir fehlen Rechte zum Leeren/Senden im Ticket-Panel-Channel.")
        except discord.DiscordException as e:
            print(f"Ticket-Panel konnte nicht zurückgesetzt werden: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
