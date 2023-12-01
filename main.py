import nextcord, time, datetime, aiohttp, dateparser, json, asyncio
from zoneinfo import available_timezones, ZoneInfo

intents = nextcord.Intents.default()
intents.message_content = True
bot = nextcord.Client(intents=intents)

good_morning = ["good morning", "gm", "hello chat"]
good_night = ["good night", "gn", "sleep well"]


gm_template = """🌄 Good morning, **{user}**!
⏰ It's currently <t:{time}:F>.

🎈 Fun stuff today:
{holidays}

🗒️ Your note for today:
{note}"""


with open("db.json", "r") as f:
    db = json.load(f)


def get_value(key):
    try:
        return db[str(key)]
    except KeyError:
        return None


def set_value(key, value):
    db[str(key)] = value
    with open("db.json", "w") as f:
        json.dump(db, f)


def get_note(user, date):
    return get_value(f"{date.strftime('%B %e %Y')} {user.id}")


def set_note(user, date, note):
    set_value(f"{date.strftime('%B %e %Y')} {user.id}", note)


def get_reminders():
    res = get_value("remind")
    return res if res else []


def add_reminder(user, date, note):
    current = get_reminders()
    if not current:
        current = []
    current.append([str(date), user.id, note])
    set_value("remind", current)


def remove_reminder(date):
    current = get_reminders()
    for i in current:
        if i[0] == str(date):
            break
    current.remove(i)
    set_value("remind", current)


def get_timezone(user):
    return get_value(str(user.id))


def set_timezone(user, timezone):
    set_value(user.id, timezone)


async def find_holidays(user):
    # get top 5 current holidays using checkiday api
    result = ""
    try:
        formatted_time = datetime.datetime.now(ZoneInfo(get_timezone(user))).strftime("%m/%d/%Y")
    except Exception:
        formatted_time = datetime.datetime.now().strftime("%m/%d/%Y")

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.checkiday.com/widget?accept_terms_and_conditions=true&date={formatted_time}"
        ) as r:
            if r.status == 200:
                js = await r.json()
                events = js["events"][:5]
                for i in events:
                    result += "- " + i["name"] + "\n"

    return result[:-1]


async def do_reminder(user, timer, message):
    now = datetime.datetime.now(ZoneInfo(get_timezone(user)))
    await asyncio.sleep((timer - now).total_seconds())
    await user.send(message)
    remove_reminder(timer)


@bot.event
async def on_ready():
    print("online")
    for i in get_reminders():
        user = await bot.fetch_user(i[1])
        bot.loop.create_task(do_reminder(user, dateparser.parse(i[0], settings={'TIMEZONE': get_timezone(user), 'RETURN_AS_TIMEZONE_AWARE': True}), i[2]))


@bot.event
async def on_message(message):
    good_morning_active = False
    good_night_active = False
    for i in good_morning:
        if message.content.lower().startswith(i):
            good_morning_active = True
    for i in good_night:
        if message.content.lower().startswith(i):
            good_night_active = True

    if good_morning_active:
        try:
            your_note = get_note(message.author, datetime.datetime.now(ZoneInfo(get_timezone(message.author))))
        except Exception:
            your_note = None
        await message.reply(
            gm_template.format(
                user=message.author,
                time=int(time.time()),
                holidays=await find_holidays(message.author),
                note=your_note
            )
        )
    elif good_night_active:
        await message.reply(f"🌌 Sleep well, **{message.author}**.")


@bot.slash_command(description="Enter your timezone.")
async def timezone(interaction, timezone: str = nextcord.SlashOption(description="Enter a valid timezone.")):
    if timezone in available_timezones():
        if "+" in timezone:
            timezone = timezone.replace("+", "-")
        elif "-" in timezone:
            timezone = timezone.replace("-", "+")
        set_timezone(interaction.user, timezone)
        sillynow = datetime.datetime.now(ZoneInfo(timezone))
        await interaction.response.send_message(f"Success! If everything is right, you should see {sillynow.strftime('%H:%M')} on your clock right now.")


@timezone.on_autocomplete("timezone")
async def autocomplete(interaction, current_input):
    current_input = current_input.lower()
    nearby_values = [i for i in available_timezones() if current_input in i.lower()]
    await interaction.response.send_autocomplete(nearby_values[:25])


@bot.slash_command(description="Reminders remind you.")
async def remind(
    interaction,
    remind_time: str = nextcord.SlashOption(
        description="This field is very smart. You can put in almost anything."
    ),
    reminder: str = nextcord.SlashOption(description="Text of your reminder!")
):
    if not get_timezone(interaction.user):
        await interaction.response.send_message("Please run `/timezone` first.", ephemeral=True)
        return
    parsed = dateparser.parse(remind_time, settings={'TIMEZONE': get_timezone(interaction.user), 'RETURN_AS_TIMEZONE_AWARE': True})
    if not parsed:
        await interaction.response.send_message("Couldn't find that time. Can you be a bit more clear?", ephemeral=True)
        return
    add_reminder(interaction.user, parsed, reminder)
    await interaction.response.send_message(f"✅ I will remind you the following <t:{int(parsed.timestamp())}:R>:\n{reminder}")
    bot.loop.create_task(do_reminder(interaction.user, parsed, reminder))


@bot.slash_command(description="Leave a note for future you.")
async def note(
    interaction,
    date: str = nextcord.SlashOption(
        description="This field is very smart. You can put in almost anything."
    ),
):
    class NoteModal(nextcord.ui.Modal):
        def __init__(self, user, date):
            super().__init__(f"A note for {date.strftime('%B %e, %Y')}", timeout=None)

            self.user = user
            self.date = date

            self.note = nextcord.ui.TextInput(
                label="Note",
                style=nextcord.TextInputStyle.paragraph,
                max_length=1000,
                default_value=get_note(user, date),
                required=False,
            )

            self.add_item(self.note)

        async def callback(self, interaction):
            set_note(self.user, self.date, self.note.value)
            await interaction.response.send_message(
                f"✅ Alright! I will show you this note on <t:{int(self.date.timestamp())}:D>:\n{self.note.value}"
            )

    if not get_timezone(interaction.user):
        await interaction.response.send_message("Please run `/timezone` first.", ephemeral=True)
        return
    parsed = dateparser.parse(date, settings={'TIMEZONE': get_timezone(interaction.user), 'RETURN_AS_TIMEZONE_AWARE': True})
    if not parsed:
        await interaction.response.send_message("Couldn't find that time. Can you be a bit more clear?", ephemeral=True)
        return
    await interaction.response.send_modal(
        NoteModal(interaction.user, parsed)
    )


@bot.slash_command(description="Anime girls help us all stay productive.")
async def waifu(interaction):
    await interaction.response.defer()
    n = ""
    if interaction.channel.is_nsfw():
        n = "n"
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.waifu.pics/{n}sfw/waifu"
        ) as r:
            js = await r.json()
            await interaction.followup.send(js["url"])


with open("token.txt", "r") as f:
	bot.run(f.read())
