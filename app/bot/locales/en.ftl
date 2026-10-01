# Bot texts. Plain Fluent messages read by FtlTranslator from
# sagenza-tgbot-sdk: `key = value`, continuation lines are indented,
# placeholders are { $name }.

error_occurred = An error occurred! Please try again
invalid_input = Invalid input!
invalid_recording_date = Could not read the recording date. Use DD.MM.YYYY, e.g. 26.07.2026, no later than today.
download_failed = ❌ MP3 was not uploaded. Check the file and try again.
episode_number_failed = ❌ Could not get the episode number: FTP did not respond.
    <code>{ $error }</code>
    Upload cancelled, start again with /start.

## Episode upload (DialogEngine dialog)

ask_typeEpisode = Hello <b>{ $first_name }</b>, what are we adding?
ask_mp3 = Loading <u><b>{ $type_episode }</b></u>. Waiting for MP3 file
got_mp3 = I see an MP3, I start downloading
done_mp3 = Here is your finished file!
set_tags = Setting tags
downloaded = MP3 downloaded! Now send the episode description according to the template below, without changing anything except the field values:
done_tag =
    Tags are set.
    Upload started, please wait about 2-5 minutes
canceled = Canceled

main_episode = Main episode
episode_aftershow = Aftershow episode

ask_template_main =
    <pre language="text">Number: { $number }
    Recording Date: 26.07.2026
    Title: Episode title
    Comment: Episode description
    Tags: Tag1, Tag2, Tag3
    Chapters: |
    00:00:07 - Introduction
    00:28:53 - Topic 1
    01:40:56 - Topic 2
    02:17:25 - Patrons and aftershow announcement</pre>
ask_template_aftershow =
    <pre language="text">Number: { $number }
    Recording Date: 26.07.2026
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
de-alert-no_session = The dialog is over, start again: /start
de-alert-stale_button = This button is outdated
de-alert-expired = The dialog has expired, start again: /start

## Audio menu

audio_ftp = FTP
audio_site = Website
audio_boosty = Boosty
audio_vk = VK Donut
audio_patreon = Patreon
audio_sponsr = Sponsr
audio_forward = Forward to chat
ftp_upload = Upload the podcast to FTP
wp_upload = Upload the podcast to the website
boosty_upload = Publish the aftershow on Boosty
vk_upload = Publish the aftershow for VK Donut
patreon_upload = Publish the aftershow on Patreon
sponsr_upload = Publish the aftershow on Sponsr
paywalled_publishing = ⏳ Publishing the aftershow on { $platform }...
forwarded = Forwarded to the chat!
forward_failed = Forwarding failed, try again later

## Admin panel

admin_panel = Admin panel
admin_bot = Bot
bot_panel = Bot management
bot_restart = Restart the bot
bot_logs = Send log files
bot_restarting = Bot is restarting
logs_failed = Error: could not collect the logs

## Service messages

admin_service = Service message
service_ask_text = Send the message text; after confirmation it goes to { $chat }
service_confirm = Send this message to { $chat }?
service_sent = Sent to { $chat }
service_failed = Could not send the message, try again later
de-button-confirm = ✅ Send

## New episode in RSS

rss_new_episode = Episode { $number } is out: { $title }. Publish it?
rss_no_mp3 = The feed has no mp3 of our episode; upload the file with /start for FTP, site and Boosty
rss_to_chat = To chat
rss_prepare = To platforms (FTP, site, Boosty)
rss_skip = Skip
rss_chat_post = New episode is out: { $title }
    { $link }
rss_done_chat = announcement sent to the chat
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
topics_panel =
    Topics and questions from listeners: one list for the hosts.
    Covered some items? Send "delete 1, 3" or tick the numbers under the list.
topics_show = 📋 Show the list
topics_add_topic = ➕ Topic
topics_add_question = ➕ Question
topics_authors = 🚷 Authors
topics_refresh = 🔄 Refresh
topics_remove_marked = 🗑 Delete ticked
topics_undo = ↩️ Restore
topics_kind_topic = TOPIC
topics_kind_question = QUESTION
topics_list_title = Topics and questions:
topics_list_empty = The list of topics and questions is empty: nobody has suggested anything yet.
topics_marked = Ticked: { $numbers }
topics_marked_none = Nothing is ticked
topics_mark_first = Tick the items with the number buttons first
topics_list_stale = This list is out of date. Here is a fresh one: tick the items there.
topics_denied = This button is for the hosts only
topics_view_missing = I do not remember which list I showed last. Here is a fresh one: take the numbers from it.
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
    The bot accepts nothing from a banned author. Their items stay on the list until you delete them.
topics_authors_empty = Nobody to ban: the list has no items from listeners and the ban list is empty.
topics_author = 🚷 { $name } (items: { $count })
topics_author_banned = ✅ Unban { $name }
topics_ban_done = The author is banned
topics_unban_done = The author is unbanned
topics_added_topic = Added your topic to the hosts' list. Thank you!
topics_added_question = Added your question to the hosts' list. Thank you!
topics_admin_added =
    Added to the list:
    { $line }
topics_reply_no_text = That message has no text, there is nothing to add.
topics_refused_too_short = Too short: at least { $min } characters, please.
topics_refused_too_long = Too long: { $max } characters at most.
topics_refused_limit = That's enough for now: up to { $limit } topics and questions a day. Try again later!
topics_refused_banned = You cannot suggest topics and questions right now.
topics_refused_duplicate = This message is already on the list.
topics_post_button = 📌 Post the "Suggest" button
topics_form_button = 💡 Suggest a topic or a question
topics_form_invite = Got a topic for an episode or a question for the hosts? Tap the button: only you will see the form.
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
    Reply to this message with your topic, { $min } to { $max } characters.
topics_form_ask_question =
    What would you like to ask the hosts?
    Reply to this message with your question, { $min } to { $max } characters.
topics_form_confirm =
    Add this to the hosts' list?
    { $kind } - { $text }
topics_form_cancelled = OK, maybe next time.
topics_form_expired = The form has expired. Start again: /topic or /question.
topics_form_open_private = Open the form in private chat
topics_form_go_private = Could not show the form here. Open it in a private chat with the bot:
