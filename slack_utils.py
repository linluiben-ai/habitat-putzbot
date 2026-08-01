"""Slack: User-Lookup, Kanal-Nachrichten, DMs und die Texte dazu."""

from slack_sdk.errors import SlackApiError

from config import (
    CONFIRM_REACTIONS,
    DECLINE_REACTIONS,
    DM_HISTORY_LIMIT,
    DRY_RUN,
    META_AUSLOSUNG,
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
    """'Nachname, Vorname' -> 'Vorname'.

    Fällt auf den vollen Titel zurück, wenn hinter dem Komma nichts steht —
    sonst stünde in der Nachricht eine leere Erwähnung.
    """
    kurz = member["name"].split(",")[-1].strip()
    return kurz or member["name"].strip().rstrip(",").strip() or "?"


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


def dm_channel(member):
    """DM-Kanal-ID für ein Mitglied (öffnet die Konversation, falls nötig)."""
    user_id = SLACK_TEST_USER_ID or get_slack_user_id(member.get("email"))
    if not user_id:
        return None
    try:
        return slack.conversations_open(users=[user_id])["channel"]["id"]
    except SlackApiError as error:
        debug(f"conversations_open für {member['name']} fehlgeschlagen: {error.response['error']}")
        return None


def send_dm(member, text, metadata=None):
    """DM an ein Mitglied. Gibt den Message-Timestamp zurück.

    `metadata` wird als Slack-Message-Metadata angehängt und kommt beim Lesen
    der Historie strukturiert zurück — so weiß der Poll-Lauf später, auf welche
    Woche sich eine Reaktion bezieht, ohne den Text parsen zu müssen.
    """
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
        channel = slack.conversations_open(users=[user_id])["channel"]["id"]
        kwargs = {"channel": channel, "text": text}
        if metadata:
            kwargs["metadata"] = metadata
        response = slack.chat_postMessage(**kwargs)
        debug(f"DM an {member['name']} gesendet (ts={response['ts']}).")
        return response["ts"]
    except SlackApiError as error:
        print(f"   ❌ Slack-Fehler (DM an {member['name']}): {error.response['error']}")
        return None


def read_dm_history(member):
    """Bot-Nachrichten samt Metadata und Reaktionen aus dem DM-Verlauf lesen.

    Gibt eine Liste von Dicts zurück, neueste zuerst:
    `{ts, event_type, payload, reaktionen, ist_vom_bot, text}`.
    """
    channel = dm_channel(member)
    if not channel:
        return []

    try:
        response = slack.conversations_history(
            channel=channel, limit=DM_HISTORY_LIMIT, include_all_metadata=True
        )
    except SlackApiError as error:
        debug(f"conversations_history für {member['name']}: {error.response['error']}")
        return []

    verlauf = []
    for message in response.get("messages", []):
        metadata = message.get("metadata") or {}
        reaktionen = {
            reaction["name"] for reaction in message.get("reactions", []) or []
        }
        verlauf.append(
            {
                "ts": message.get("ts"),
                "text": message.get("text", ""),
                # bot_id gesetzt = von uns, sonst vom Mitglied geschrieben
                "ist_vom_bot": bool(message.get("bot_id")),
                "event_type": metadata.get("event_type"),
                "payload": metadata.get("event_payload") or {},
                "reaktionen": reaktionen,
            }
        )

    # Die eine Annahme, auf der der ganze Reschedule-Flow steht: dass Slack die
    # Metadata über conversations_history zurückgibt. Kommt hier 0 heraus,
    # obwohl Bot-Nachrichten dabei sind, fehlt entweder ein Scope oder die
    # Nachrichten stammen von einer Version ohne Metadata.
    vom_bot = sum(1 for e in verlauf if e["ist_vom_bot"])
    mit_meta = sum(1 for e in verlauf if e["event_type"])
    debug(
        f"DM-Verlauf {member['name']}: {len(verlauf)} Nachrichten, "
        f"{vom_bot} vom Bot, {mit_meta} mit Metadata."
    )
    return verlauf


def reaktion_auf(eintrag):
    """'ja' / 'nein' / None — was hat das Mitglied auf diese Nachricht geklickt?"""
    if eintrag["reaktionen"] & DECLINE_REACTIONS:
        return "nein"
    if eintrag["reaktionen"] & CONFIRM_REACTIONS:
        return "ja"
    return None


def auslosung_metadata(member, kw, year):
    return {
        "event_type": META_AUSLOSUNG,
        "event_payload": {"kw": kw, "jahr": year, "mitglied": member["id"]},
    }


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
            "Reagier einfach mit dem passenden Emoji auf diese Nachricht. "
            "Ich schaue mehrmals am Tag nach, es kann also ein paar Stunden dauern, "
            "bis ich mich melde."
        )
    else:
        text += (
            "\n\nWenn es dir nicht passt, meld dich bitte kurz im Team — "
            "das automatische Verschieben kommt noch."
        )
    if page_url:
        text += f"\n\n👉 <{page_url}|Zur Woche in Notion>"
    return text


def build_wochen_auslosung(kw, bestehend, gelost, page_url):
    """Kanalnachricht für den Übergangsmodus `draw` — eine Woche, keine DMs.

    Bewusst im Ton der alten V2-Nachricht: solange es noch keine DMs gibt, ist
    das hier die einzige Stelle, an der jemand von seinem Einsatz erfährt.
    """
    text = f"🧹 *Der Putzplan für KW {kw} ist da* 🧹\n\n"

    if not bestehend and not gelost:
        text += (
            "Für diese Woche ist noch niemand eingetragen und es konnte auch "
            "niemand ausgelost werden. Wer mag spontan übernehmen?"
        )
    elif not gelost:
        text += (
            f"Diese Woche sind wir schon komplett — danke an die Freiwilligen: "
            f"{mention_list(bestehend)} 💚"
        )
    else:
        if bestehend:
            text += f"Danke fürs freiwillige Eintragen: {mention_list(bestehend)} 🙏\n"
        text += f"Ausgelost wurden: {mention_list(gelost)} 🎲"

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


def build_reschedule_frage(member, kw, max_kw_hinweis):
    """Nachfrage, nachdem jemand mit ❌ reagiert hat."""
    return (
        f"Alles klar {vorname(member)}, KW {kw} passt dir also nicht. 👍\n\n"
        f"In welcher Woche möchtest du stattdessen putzen?\n"
        f"Antworte einfach mit der Kalenderwoche als Zahl, z.B. `{max_kw_hinweis}`.\n\n"
        f"_Du bleibst so lange in KW {kw} eingetragen, bis du dich für eine neue Woche "
        f"entschieden hast — damit die Woche nicht plötzlich unbesetzt ist._"
    )


def build_reschedule_ok(member, alte_kw, neue_kw, page_url):
    text = (
        f"Erledigt! Du bist jetzt statt in KW {alte_kw} in *KW {neue_kw}* eingetragen. ✅"
    )
    if page_url:
        text += f"\n\n👉 <{page_url}|Zur neuen Woche in Notion>"
    return text


def build_reschedule_fehler(member, eingabe, grund, max_kw_hinweis, link=None):
    """Absage auf eine Wunschwoche, verbunden mit einer erneuten Nachfrage.

    Der Einstieg ist bewusst neutral: dieselbe Funktion bedient unverständliche
    Eingaben *und* verstandene, aber unbrauchbare Wochen (voll, gesperrt, in der
    Vergangenheit). Ein „damit kann ich nichts anfangen" wäre im zweiten Fall
    schlicht falsch — der Bot hat die KW ja verstanden.
    """
    text = (
        f"Das klappt leider nicht mit `{eingabe}`: {grund}\n\n"
        f"Antworte bitte nochmal mit einer Kalenderwoche als Zahl, z.B. "
        f"`{max_kw_hinweis}`."
    )
    if link:
        text += (
            f"\n\n👉 <{link}|Hier siehst du die Woche in Notion> — "
            f"such dir von dort eine mit weniger als 4 Leuten aus."
        )
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
