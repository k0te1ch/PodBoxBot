cancel = Cancel
back = Back
error_occurred = An error occurred! Please try again
invalid_input = Invalid input!
download_failed = ❌ MP3 was not uploaded. Check the file and try again.

ask_typeEpisode = Hello <b>{msg.from_user.first_name}</b>, what are we adding?
ask_mp3 = Loading <u><b>{type_episode}</b></u>. Waiting for MP3 file
got_mp3 = I see an MP3, I start downloading
done_mp3 = Here is your finished file!
set_tags = Setting tags
downloaded = MP3 downloaded! Now send the episode description according to the template below, without changing anything except the field values:
done_tag = Tags are set.\nUpload started, please wait about 2-5 minutes
canceled = Canceled

main_episode = Main episode
episode_aftershow = Aftershow episode

admin_panel_opened = Admin panel
admin_panel_open = Admin panel
admin_panel_close = Admin panel closed
admin_panel_main = [["Bot", "botPanel"]]
bot_commands = [["Turn off the bot", "shutdown_bot"], ["Send log files", "send_logs"]]

ask_template = {
    .main = |
        <pre language="text">Number: 600
        Title: Episode title
        Comment: Episode description
        Tags: Tag1, Tag2, Tag3
        Chapters: |
        00:00:07 - Introduction
        00:28:53 - Topic 1
        01:40:56 - Topic 2
        02:17:25 - Patrons and aftershow announcement</pre>
    .aftershow = |
        <pre language="text">Number: 600
        Title: Aftershow. Episode title
        Comment: Episode description</pre>
}
