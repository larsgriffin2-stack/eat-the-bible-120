# Eat The Bible 120

Eat The Bible 120 is a daily Bible reading podcast following the Eat The Bible 120 reading plan. Each episode presents selected readings from the Old Testament, New Testament, Psalms, and Proverbs, helping listeners engage with Scripture consistently throughout the year.

This podcast uses the World English Bible (WEB), a public-domain modern English translation. Visit https://worldenglish.bible/ for more information and resources.

## Feed

Once GitHub Pages is enabled, the podcast feed will be available at:

`https://larsgriffin2-stack.github.io/eat-the-bible-120/rss.xml`

This repository also publishes the podcast artwork at `cover.jpg`; the RSS feed references it through both the standard RSS `<image>` element and Apple Podcasts' `itunes:image` element.

## Local workflow

Audio episodes belong in `audio/` as MP3 files. Regenerate the feed with:

```bash
python3 generator.py
```

To regenerate, commit, and push after GitHub authentication is configured:

```bash
./publish.sh
```

The generator reads MP3 duration and byte size, creates Apple Podcasts-compatible RSS 2.0 metadata, and uses the episode filename (`day-001.mp3`, etc.) for numbering.
