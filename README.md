# Rekolekt

![Rekolekt: The sentence, and where it was said. Green index mark on a dark archive field.](https://git.subcult.tv/api/v1/repos/subculture-collective/rekolekt/raw/docs/assets/readme/banner.png?ref=050194e739f35554a0b22db4abd22a52359d694f)

Rekolekt is software for running an archive of long recordings. It transcribes
each recording with timestamps, indexes the text, and links every passage back
to the second it was spoken in the source video.

This repository is the headless core: the backend services and the HTTP API.
It ships no web pages. Each archive builds and owns its own frontend against the
API contract in [`docs/api/openapi.json`](docs/api/openapi.json).

You deploy it yourself; it is not a hosted upload service. It suits people who
maintain a collection and want others to search and cite it: a creator with a
back catalog, a research group, a community keeping its own reference.

[Explore Rekolekt](https://subcult.tv/products/rekolekt) · [See it in use at HasanAra](https://hasanara.tv) · [Suggest a feature](https://git.subcult.tv/subculture-collective/rekolekt/issues)

## What it does

- **Transcript and index:** videos are ingested and transcribed into timestamped
  text that the API serves for browsing and search.
- **Source link:** search results carry the video and timestamp, so a frontend
  can open the original player with the surrounding transcript.
- **Passage link:** the API resolves a start and end into a shareable passage
  that restores the range and context. Basic passage links need no account.
- **Saves and exports:** accounts can save searches and moments, and export
  transcript text for further work.
- **Site profile:** each archive supplies its own name, description, notices and
  artwork URLs, served at `/site`.

Transcripts are machine-made and can contain errors; check the recording before
quoting. Passage links point to the currently available source and transcript;
they are not immutable citations or downloaded video clips. See the [passage-sharing guide](docs/product/passage-sharing.md).

## Each archive runs its own frontend

[HasanAra](https://hasanara.tv) runs on Rekolekt with its own identity, broadcast
sources and web interface. An archive deploys the core release images for the
backend roles and builds its own frontend. The
[`rekolekt-web`](https://git.subcult.tv/subculture-collective/rekolekt-web) kit
provides the API client, generated types, hooks and stylable default components,
with no pages. Its `archive/reference-app-ae1cc82` branch keeps the designed
application that used to live in this repository. Available features depend on
the deployment's server settings.

The repository is now `subculture-collective/rekolekt`; historical deployment
identifiers may still use `transcript-create`.

## Run your own or contribute

Local development requires Python 3.11 and Docker with Compose.
For ingestion, deployment configuration, local setup and verification, the
[development guide](DEVELOPMENT.md) covers setup and the canonical `make verify`
gate.

- [Client branding and deployment](docs/deployment/client-branding.md)
- [Testing guide](docs/development/testing.md)
- [API reference](docs/api-reference.md) and [OpenAPI contract](docs/api/openapi.json)
- [Documentation index](docs/STATUS.md)

Built by [Subcult](https://subcult.tv). Licensed under [Apache-2.0](LICENSE), with
[third-party notices](docs/THIRD_PARTY_NOTICES.md).
