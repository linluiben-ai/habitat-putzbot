"""Slack: User-Lookup, Kanal-Nachrichten, DMs und die Texte dazu."""

from slack_sdk.errors import SlackApiError

from config import (
    DRY_RUN,
    RESCHEDULE_ENABLED,
    SLACK_CHANNEL_ID,
    SLACK_TEST_USER_ID,
    debug,
    slack,
)

_user_id_cache = {}


def get_slack_user_id(email):
    """Slack-User-ID zu einer E-Mail. Ergebnis wird gecacht (auch Fehlschläge)."""
    if not email:
        return None
    if email in _user_id_cache:
        return _user_id_cache[email]

    try:
        result = slack.users_lookupByEmail(email=email)
        user_id = result["user"]["id"]
    except SlackApiError as error:
        debug(f"Kein Slack-User für {email}: {error.response['error']}")
        user_id = None

    _user_id_cache[email] = user_id
    return user_id


def vorname(member):
    """'Nachname, Vorname' -> 'Vorname'."""
    return member["name"].split(",")[-1].strip()


def mention(member):
    """@-Erwähnung, sonst der Vorname als Fallback."""
    user_id = get_slack_user_id(member.get("email"))
    return f"<@{user_id}>" if user_id else vorname(member)


def mention_list(members):
    return ", ".join(mention(m) for m in members)


def post_channel(text, channel=None):
    channel = channel or SLACK_CHANNEL_ID
    if DRY_RUN:
        print(f"   🧪 [DRY RUN] Kanal-Nachricht an {channel}:\n{_indent(text)}")
        return True

    try:
        slack.chat_postMessage(channel=channel, text=text)
        print("   📨 Slack-Nachricht in den Kanal gesendet.")
        return True
    except SlackApiError as error:
        print(f"   ❌ Slack-Fehler (Kanal): {error.response['error']}")
        return False


def send_dm(member, text):
    """DM an ein Mitglied. Gibt den Message-Timestamp zurück (für spätere Reaktionen)."""
    if SLACK_TEST_USER_ID:
        text = f"_[Test-DM, eigentlich an {member['name']}]_\n\n{text}"
        user_id = SLACK_TEST_USER_ID
    else:
        user_id = get_slack_user_id(member.get("email"))

    if not user_id:
        print(f"   ⚠️ Keine Slack-ID für {member['name']} — keine DM verschickt.")
        return None

    if DRY_RUN:
        print(f"   🧪 [DRY RUN] DM an {member['name']} ({user_id}):\n{_indent(text)}")
        return None

    try:
        conversation = slack.conversations_open(users=[user_id])
        response = slack.chat_postMessage(channel=conversation["channel"]["id"], text=text)
        debug(f"DM an {member['name']} gesendet (ts={response['ts']}).")
        return response["ts"]
    except SlackApiError as error:
        print(f"   ❌ Slack-Fehler (DM an {member['name']}): {error.response['error']}")
        return None


def _indent(text):
    return "\n".join(f"      | {line}" for line in text.splitlines())


# --- Nachrichtentexte ---

def build_draw_dm(member, kw, page_url):
    """DM an ein frisch ausgelostes Mitglied."""
    text = (
        f"Hallo {vorname(member)}! 🧹\n\n"
        f"Du wurdest für die Putzcrew in *KW {kw}* ausgelost. "
        f"Du bist damit schon für diese Woche eingetragen."
    )
    if RESCHEDULE_ENABLED:
        text += (
            "\n\nPasst dir die Woche?\n"
            "✅ = passt, ich bin dabei\n"
            "❌ = ich möchte in einer anderen Woche putzen\n\n"
            "Reagier einfach mit dem passenden Emoji auf diese Nachricht."
        )
    else:
        text += (
            "\n\nWenn es dir nicht passt, meld dich bitte kurz im Team — "
            "das automatische Verschieben kommt noch."
        )
    if page_url:
        text += f"\n\n👉 <{page_url}|Zur Woche in Notion>"
    return text


def build_reminder(kw, crew, page_url):
    """Wöchentliche Erinnerung in den Kanal."""
    if not crew:
        text = (
            f"🧹 *Putzplan KW {kw}* 🧹\n\n"
            f"Für diese Woche ist noch niemand eingetragen. "
            f"Wer mag spontan übernehmen?"
        )
    else:
        text = (
            f"🧹 *Putzplan KW {kw}* 🧹\n\n"
            f"Diese Woche seid ihr dran: {mention_list(crew)} 💚"
        )
    if page_url:
        text += f"\n\n👉 <{page_url}|Zur Woche in Notion>"
    return text


def build_cycle_summary(cycle, year, per_week):
    """Zusammenfassung nach dem Plan-Lauf: wer putzt im nächsten Zyklus wann.

    `per_week` ist eine Liste von (kw, crew, page_url).
    """
    text = f"🗓️ *Putzplan für Zyklus {cycle}/{year} steht* 🗓️\n\n"
    for kw, crew, page_url in per_week:
        names = mention_list(crew) if crew else "_noch offen_"
        line = f"• *KW {kw}*: {names}"
        if page_url:
            line = f"• *<{page_url}|KW {kw}>*: {names}"
        text += line + "\n"
    text += (
        "\nDie Ausgelosten haben eine DM bekommen. "
        "Wer tauschen möchte, meldet sich bitte frühzeitig 🙏"
    )
    return text
