# Eat The Bible 120

Daily Bible reading podcast from the Eat The Bible 120 reading plan.

## Feed

Once GitHub Pages is enabled, the podcast feed will be available at:

`https://larsgriffin2.github.io/eat-the-bible-120/rss.xml`

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
