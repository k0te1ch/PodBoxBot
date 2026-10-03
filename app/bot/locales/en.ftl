# Bot texts. Plain Fluent messages read by FtlTranslator from
# sagenza-tgbot-sdk: `key = value`, continuation lines are indented,
# placeholders are { $name }.

error_occurred = Something went wrong, try again
invalid_input = Could not read the description. Check that the Number, Title and Comment lines are in place, as in the template
invalid_recording_date = Could not read the recording date. Pick it with a button or type DD.MM.YYYY, e.g. 26.07.2026, no later than today
invalid_publish_at = Could not read the publication date. Pick it with the buttons or type the date and time, e.g. 05.10.2026 20:00, not earlier than now
download_failed = did not download. Check the file and send it again
episode_number_failed = FTP did not respond, the upload is cancelled. Start again: /new
    <code>{ $error }</code>

## Episode upload (DialogEngine dialog)

ask_typeEpisode = Which episode are we preparing?
ask_typeEpisode_for_file = I see an MP3. Is it the main episode or the aftershow?
file_not_mp3 = This is not an MP3. To prepare an episode, send an MP3 or press "New episode" in /start
ask_mp3 = Preparing: <b>{ $type_episode }</b>. Send the MP3
got_mp3 = I see an MP3, downloading
done_mp3 = The episode is ready. Where do we publish?
canceled = Cancelled

## Episode dates (utils/date_picker.py)

summary_file = ✅ File received ({ $size }), this will be episode { $number }
summary_recording = Episode { $number } · recorded { $recording }
summary_dates = Episode { $number } · recorded { $recording } · publication { $publish }
ask_recording_date = When was the episode recorded?
ask_publish_at = When do we publish? "As usual": no date is set, the site keeps a draft, the other platforms act right away
date_today = Today, { $date }
date_yesterday = Yesterday, { $date }
date_other = 📅 Another date
date_back = « Back to quick choice
date_publish_default = As usual
date_publish_default_short = as usual
date_publish_today = Today
date_publish_tomorrow = Tomorrow
date_day_month = { $month } { $day }
months = January February March April May June July August September October November December
months_genitive = January February March April May June July August September October November December
weekdays = Mo Tu We Th Fr Sa Su

## Status message of a long operation (utils/status_message.py)

status_download = Downloading the file
status_download_done = File received
status_number = Looking up the episode number
status_number_done = Episode number is known
status_description = Next: the episode description
status_tags = Setting tags and the cover
status_tags_done = Tags and the cover are set
status_send = Sending the finished file
status_send_done = File sent
status_episode_title = 🎙 { $title }
status_tags_failed = did not work. Start again: /new
    <code>{ $error }</code>
status_send_failed = Telegram did not accept the file. Start again: /new
    <code>{ $error }</code>
status_kilobytes = KB
status_megabytes = MB
status_seconds = { $seconds } s
status_minutes = { $minutes } min { $seconds } s
status_of = { $done } of { $total }
status_left = ~{ $time } left
status_slow = { $time } already, longer than usual, still waiting

main_episode = Main episode
episode_aftershow = Aftershow

ask_template_main =
    Now send the description. Copy the template and change only the values:
    <pre language="text">Number: { $number }
    Title: Episode title
    Comment: Episode description
    Tags: Tag1, Tag2, Tag3
    Chapters: |
    00:00:07 - Introduction
    00:28:53 - Topic 1
    01:40:56 - Topic 2
    02:17:25 - Patrons and aftershow announcement</pre>
ask_template_aftershow =
    Now send the description. Copy the template and change only the values:
    <pre language="text">Number: { $number }
    Title: Aftershow. Episode title
    Comment: Episode description</pre>

# DialogEngine service texts: key `de.x.y` is looked up as `de-x-y`.
# Their placeholders use plain braces, the engine fills them in.
de-button-back = ⬅️ Back
de-button-cancel = Cancel
de-button-keep = Keep
de-button-keep_value = Keep: {value}
de-error-media-mime = An MP3 is required (allowed types: {allowed})
de-error-media-extension = A file with extension {allowed} is required
de-error-media-size = The file is larger than {max_mb} MB
de-error-file-expected = Waiting for an MP3 file
de-error-media-unexpected = Text is expected here, not a file
de-error-button_required = Pick an option with a button
de-alert-no_session = This dialog is over. New episode: /new
de-alert-stale_button = This button is outdated
de-alert-expired = The dialog has expired. New episode: /new

## Audio menu

audio_ftp = FTP
audio_site = Website
audio_boosty = Boosty
audio_vk = VK Donut
audio_patreon = Patreon
audio_sponsr = Sponsr
audio_forward = To the chat
ftp_upload = Upload to FTP
wp_upload = Save a draft on the site
boosty_upload = Publish the aftershow on Boosty
vk_upload = Publish the aftershow for VK Donut
patreon_upload = Publish the aftershow on Patreon
sponsr_upload = Publish the aftershow on Sponsr
forwarded = Forwarded to the chat
forward_failed = Could not forward, the reason is in the message below

## Admin panel

home_admin = Hi! What are we doing?
home_user = Hi! This is the podcast bot. Here you can suggest a topic for an episode or ask the hosts a question
home_new_episode = 🎙 New episode
home_admin_panel = ⚙️ Admin
home_help = ❓ How it works
help_text =
    Send /topic to suggest a topic for an episode, or /question to ask the hosts a question.
    You can add the text right away: /question why is the sky blue?
    The hosts see everything in one list and pick it up in one of the episodes

admin_panel = Admin
bot_restart = Restart
bot_logs = Logs
bot_restarting = Bot is restarting
logs_failed = Error: could not collect the logs

## Service messages

admin_service = Message to the chat
service_ask_text = Send the message text; after confirmation it goes to { $chat }
service_confirm = Send this message to { $chat }?
service_sent = Sent to { $chat }
service_failed = Could not send the message, try again later
de-button-confirm = ✅ Send

## New episode in RSS

rss_new_episode = Episode { $number } is out: { $title }. Publish it?
rss_no_mp3 = The feed has no mp3 of our episode; upload the file with /start for FTP, site and Boosty
rss_to_chat = To chat
rss_prepare = To the platforms
rss_skip = Skip
rss_chat_post = A new episode is out: <a href="{ $link }">{ $title }</a>
rss_download_failed = the MP3 did not download, try later
rss_done_chat = announcement sent to { $chat }
rss_done_prepare = mp3 downloaded, pick a platform in the menu under the file
rss_done_skip = skipped
rss_cannot_prepare = no mp3 or episode number, upload the file with /start
rss_choice = { $user }: { $result }
rss_expired = This notification is outdated
rss_feed_down = RSS feed failed { $count } times in a row: { $url }

## Host notes

admin_notes = Host notes
notes_groups = Host notes by group. Add one: /note #topic text
notes_entries = Notes in group
notes_usage = Write the note after the command: /note #topic text. Groups: { $tags }
collector_saved = Saved to #{ $tag }
collector_used = ✅ Used
collector_delete = 🗑 Delete
collector_marked_used = Marked as used
collector_deleted = Deleted
collector_missing = The entry is already gone
collector_open_message = Open message

## Topics and questions from listeners

admin_topics = 💡 Topics and questions
topics_panel = Topics and questions from listeners
topics_show = 📋 List
topics_add_topic = ➕ Topic
topics_add_question = ➕ Question
topics_authors = 🚷 Authors
topics_refresh = 🔄 Refresh
topics_remove_marked = Delete ticked ({ $count })
topics_undo = ↩️ Restore
topics_kind_topic = TOPIC
topics_kind_question = QUESTION
topics_list_heading = Topics and questions
topics_column_number = No
topics_column_kind = Kind
topics_column_text = Text
topics_column_author = From
topics_column_when = When
topics_list_title = Topics and questions:
topics_list_empty = The list of topics and questions is empty: nobody has suggested anything yet
topics_marked = Ticked: { $numbers }
topics_marked_count = Items ticked: { $count }
topics_marked_none = Nothing is ticked
topics_mark_first = Tick the items with the number buttons first
topics_list_stale = This list is out of date. Here is a fresh one: tick the items there
topics_denied = This button is for the hosts only
topics_view_missing = I do not remember which list I showed last. Here is a fresh one: take the numbers from it
topics_numbers_unknown = The last list has { $total } items and no such numbers: { $numbers }. Nothing was deleted. Fresh list: /topics
topics_remove_usage = Send the item numbers from the last list: /done 1 3 4 or "delete 1, 3, 4". The list: /topics
topics_removed = Deleted from the list:
topics_removed_more = … and { $count } more
topics_removed_gone = Already deleted earlier: { $numbers }
topics_removed_nothing = These items are no longer on the list, they were deleted earlier: { $numbers }
topics_restored = Back on the list:
topics_undo_expired = Too late to restore: more than 10 minutes have passed or the items are already back
topics_authors_title =
    Authors of the listed items and the ban list. Tap an author to ban or unban them.
    The bot accepts nothing from a banned author. Their items stay on the list until you delete them
topics_authors_empty = Nobody to ban: the list has no items from listeners and the ban list is empty
topics_author = 🚷 { $name } (items: { $count })
topics_author_banned = ✅ Unban { $name }
topics_ban_done = The author is banned
topics_unban_done = The author is unbanned
topics_added_topic = Added your topic to the hosts' list. Thank you!
topics_added_question = Added your question to the hosts' list. Thank you!
topics_admin_added =
    Added to the list:
    { $line }
topics_reply_no_text = That message has no text, there is nothing to add
topics_refused_too_short = Too short: at least { $min } characters, please
topics_refused_too_long = Too long: { $max } characters at most
topics_refused_limit = That's enough for now: up to { $limit } topics and questions a day. Try again later!
topics_refused_banned = You cannot suggest topics and questions right now
topics_refused_duplicate = This message is already on the list
topics_post_button = 📌 Post the "Suggest" button
topics_form_button = 💡 Suggest a topic or a question
topics_form_invite = Got a topic for an episode or a question for the hosts? Tap the button: only you will see the form
topics_form_posted = Button posted to { $chat }
topics_form_post_failed = Could not post the button. Is the bot in the chat and allowed to write there?
topics_form_command = Suggest a topic or a question to the hosts
topics_form_command_topic = Suggest a topic for an episode
topics_form_command_question = Ask the hosts a question
topics_form_kind = What should go on the hosts' list?
topics_form_kind_topic = 💡 A topic
topics_form_kind_question = ❓ A question
topics_form_ask_topic =
    What should the hosts talk about?
    Reply to this message with your topic, { $min } to { $max } characters
topics_form_ask_question =
    What would you like to ask the hosts?
    Reply to this message with your question, { $min } to { $max } characters
topics_form_ask_topic_admin =
    Which topic should go on the list?
    Send it as your next message, up to { $max } characters
topics_form_ask_question_admin =
    Which question should go on the list?
    Send it as your next message, up to { $max } characters
topics_form_confirm =
    Add this to the hosts' list?
    { $kind } - { $text }
topics_form_cancelled = OK, maybe next time
topics_form_expired = The form has expired. Start again: /topic or /question
topics_form_open_private = Open the form in private chat
topics_form_go_private = Could not show the form here. Open it in a private chat with the bot:

## /status

status_title = PodBoxBot: status
status_version = Version
status_uptime = Uptime
status_updates = Updates handled
status_errors = Errors
status_rss = Feed watcher
status_topics = Topics and questions on the list
status_on = on
status_off = off
status_publications = Recent publications
status_publications_none = No publications since the bot started
status_column_what = What
status_column_value = Value
status_column_episode = Episode
status_column_platform = Platform
status_column_state = State
status_column_when = When

## Stale buttons

episode_file_gone = This file has been replaced by a newer episode. To publish it, prepare the episode again: /new
publish_sent = Sent, the status is below
publish_send_failed = Could not send the request, the reason is in the status below
