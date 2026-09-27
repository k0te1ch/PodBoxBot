# Bot texts. Plain Fluent messages read by FtlTranslator from
# sagenza-tgbot-sdk: `key = value`, continuation lines are indented,
# placeholders are { $name }.

error_occurred = An error occurred! Please try again
invalid_input = Invalid input!
invalid_recording_date = Could not read the recording date. Use DD.MM.YYYY, e.g. 26.07.2026, no later than today.
download_failed = ❌ MP3 was not uploaded. Check the file and try again.

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
audio_forward = Forward to chat
ftp_upload = Upload the podcast to FTP
wp_upload = Upload the podcast to the website
boosty_upload = Publish the aftershow on Boosty
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

## Host notes and listener questions

admin_notes = Host notes
admin_questions = Listener questions
notes_groups = Host notes by group. Add one: /note #topic text
questions_groups = Listener questions and topics by hashtag
notes_entries = Notes in group
questions_entries = Questions in group
notes_usage = Write the note after the command: /note #topic text. Groups: { $tags }
questions_usage = Write your question after the command: /ask text. You may add a hashtag: { $tags }
collector_saved = Saved to #{ $tag }
collector_used = ✅ Used
collector_delete = 🗑 Delete
collector_marked_used = Marked as used
collector_deleted = Deleted
collector_missing = The entry is already gone
collector_open_message = Open message
