# Rekolekt

**Searchable recordings. Quotable moments. Source intact.**

Rekolekt turns long-form recordings into a searchable transcript archive. Find
what was said, return to the timestamp in the source video, and save or share a
passage with its context.

It is built for creators, researchers, and communities who want recorded
conversations to stay useful after the broadcast ends.

[Explore Rekolekt](https://subcult.tv/products/transcript-create) · [See it in use at HasanAra](https://hasanara.tv) · [Suggest a feature](https://git.subcult.tv/subculture-collective/transcript-create/issues)

## Turn an archive into something people can use

- **Make recordings searchable:** ingest videos and build timestamped transcripts
  that visitors can browse and search.
- **Keep the source close:** open results in the original player and read the
  surrounding transcript.
- **Share a passage:** choose a start and end, preview the selection, and copy a
  link that restores the range and context. Basic passage links need no account.
- **Build a personal reference:** save searches and moments, and export transcript
  text for further work.
- **Make it your archive:** supply a public brand profile, artwork, and theme
  while using the same application core.

Automated transcription can contain errors. Passage links point to the currently
available source and transcript; they are not immutable citations or downloaded
video clips. See the [passage-sharing guide](docs/product/passage-sharing.md).

## One application, distinct archives

[HasanAra](https://hasanara.tv) runs on Rekolekt with its own identity and broadcast
sources. Other archives can supply their own branding without maintaining a
source fork or rebuilding the frontend. Available features depend on the
deployment's server settings.

The source repository retains the name `transcript-create`.

## Run your own or contribute

The application uses React, FastAPI, PostgreSQL, and transcription workers.
Local development requires Python 3.11, Node.js 20, and Docker with Compose.
The [development guide](DEVELOPMENT.md) covers setup and the canonical `make verify`
gate.

- [Client branding and deployment](docs/deployment/client-branding.md)
- [Testing guide](docs/development/testing.md)
- [API reference](docs/api-reference.md)
- [Documentation index](docs/STATUS.md)

Built by [Subcult](https://subcult.tv). Licensed under [Apache-2.0](LICENSE), with
[third-party notices](docs/THIRD_PARTY_NOTICES.md).
