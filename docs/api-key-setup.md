# API key setup

`yt-research` requires a YouTube Data API v3 key for public API requests.

1. Create or select a project in Google Cloud Console.
2. Enable **YouTube Data API v3** for the project.
3. Create an API key under **APIs & Services > Credentials**.
4. Restrict the key to the YouTube Data API v3. Apply any additional restrictions that fit your environment.
5. Run `yt-research auth set` and paste the key into the hidden prompt.

Check or remove the stored credential with:

```console
yt-research auth status
yt-research auth delete
```

On a headless Linux host without a native keyring, use an environment variable:

```console
export YT_RESEARCH_API_KEY="your-api-key"
```

The environment variable takes precedence over the keyring. Avoid placing it in shell history, committed environment files, or CI logs. Use your CI provider's encrypted secret storage.

